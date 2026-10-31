//! Reads only a caller-supplied, bounded crop of the visible pickup log.
use image::{GrayImage, Luma, RgbaImage};
use minerva_core::Frame;
use serde_json::{Value, json};
use std::collections::{HashMap, hash_map::DefaultHasher};
use std::hash::{Hash, Hasher};

const MAX_OCR_CALLS: usize = 12;
const MAX_CACHE_ENTRIES: usize = 256;

#[derive(Clone, Debug, PartialEq)]
struct Message {
    key: String,
    mesos: Option<u32>,
    kind: &'static str,
}

#[derive(Default)]
pub struct PickupLogReader {
    cache: HashMap<(u32, u32, Vec<u8>), Option<Message>>,
}

fn amount(text: &str) -> Option<u32> {
    if text.is_empty() || !text.bytes().all(|b| b.is_ascii_digit() || b == b',') {
        return None;
    }
    let groups = text.split(',').collect::<Vec<_>>();
    if groups.len() > 1
        && (groups[0].is_empty() || groups[0].len() > 3 || groups[1..].iter().any(|s| s.len() != 3))
    {
        return None;
    }
    let digits = text.replace(',', "");
    if digits.len() > 1 && digits.starts_with('0') {
        return None;
    }
    let value = digits.parse::<u32>().ok()?;
    (value > 0 && value <= 2_147_483_647).then_some(value)
}

fn message(text: &str) -> Option<Message> {
    let text = text
        .trim()
        .trim_end_matches('.')
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_ascii_lowercase();
    for (prefix, kind) in [
        ("you have gained mesos (+", "meso"),
        ("you received exp (+", "exp"),
        ("you have gained experience (+", "exp"),
        ("bonus exp for party (+", "party_exp"),
    ] {
        if let Some(value) = text.strip_prefix(prefix).and_then(|s| s.strip_suffix(')')) {
            let value = amount(value)?;
            return Some(Message {
                key: format!("{}:{value}", if kind == "meso" { "mesos" } else { kind }),
                mesos: (kind == "meso").then_some(value),
                kind,
            });
        }
    }
    // Item receipts only anchor movement. Neither their quantity nor any other
    // number in a non-meso message may contribute to the currency total.
    if !text.contains(':') {
        for category in ["etc", "use", "equip", "setup", "cash"] {
            if let Some(receipt) = text.strip_suffix(&format!(" earned. ({category})")) {
                // The multiplication marker is sometimes omitted by OCR. This
                // is only a non-currency movement anchor; never infer an amount
                // of mesos from an item quantity or repair its numeric digits.
                let parts = receipt
                    .rsplit_once(' ')
                    .or_else(|| receipt.rsplit_once('x'));
                if let Some((name, quantity)) = parts {
                    let quantity = quantity.trim().strip_prefix('x').unwrap_or(quantity.trim());
                    if name.trim().len() >= 2 && amount(quantity).is_some() {
                        return Some(Message {
                            key: format!("item:{text}"),
                            mesos: None,
                            kind: "item",
                        });
                    }
                }
            }
        }
    }
    None
}

/// Restrict ink to neutral/yellow pixels with a nearby darker outline. Relative
/// contrast retains the game font as it fades, without treating flat panels or
/// uniformly bright scenery as letters.
fn ink_components(image: &RgbaImage, x: u32, y: u32) -> (u8, u8) {
    let p = image.get_pixel(x, y).0;
    let brightness = p[0].min(p[1]);
    if brightness < 32 && p[2] < 32 {
        return (0, 0);
    }
    let mut outline = 255;
    let mut blue_outline = 255;
    for dy in -2i32..=2 {
        for dx in -2i32..=2 {
            let nx = x as i32 + dx;
            let ny = y as i32 + dy;
            if nx >= 0 && ny >= 0 && nx < image.width() as i32 && ny < image.height() as i32 {
                let q = image.get_pixel(nx as u32, ny as u32).0;
                outline = outline.min(q[0].max(q[1]).max(q[2]));
                blue_outline = blue_outline.min(q[2]);
            }
        }
    }
    // White glyphs change R/G hue as they fade over brown scenery. Local blue
    // contrast preserves their exact shape; keep yellow EXP ink separate.
    let white = if p[2] >= 32 && p[2].saturating_sub(blue_outline) >= 18 {
        p[2]
    } else {
        0
    };
    let yellow = if white != 0
        || brightness < 32
        || p[0].abs_diff(p[1]) > brightness / 8 + 8
        || p[2] > p[0].saturating_add(35)
        || outline > 80
        || brightness.saturating_sub(outline) < 18
    {
        0
    } else {
        brightness
    };
    (white, yellow)
}

fn bands_from(mask: &GrayImage, left: u32) -> Vec<(u32, u32)> {
    // The log is right-aligned. Scenery, names and the quick-slot bar on the
    // left of this bounded crop must not join separate text rows together.
    let mut result = Vec::new();
    let mut y = 0;
    while y < mask.height() {
        if (left..mask.width())
            .filter(|&x| mask.get_pixel(x, y).0[0] != 0)
            .count()
            < 3
        {
            y += 1;
            continue;
        }
        let top = y;
        let mut bottom = y + 1;
        let mut blank = 0;
        y += 1;
        while y < mask.height() && blank < 3 {
            if (left..mask.width())
                .filter(|&x| mask.get_pixel(x, y).0[0] != 0)
                .count()
                >= 2
            {
                bottom = y + 1;
                blank = 0;
            } else {
                blank += 1;
            }
            y += 1;
        }
        if (6..=28).contains(&(bottom - top)) {
            result.push((top, bottom));
        }
    }
    result
}

fn bands(mask: &GrayImage) -> Vec<(u32, u32)> {
    // The last few glyphs sit beyond most world artwork. Use them to separate
    // rows; still OCR the complete row, including its strict system prefix.
    let edge = bands_from(mask, mask.width().saturating_sub(96));
    if edge.is_empty() {
        bands_from(mask, mask.width().saturating_sub(320))
    } else {
        edge
    }
}

fn normalized_patch(strength: &GrayImage, x: u32, y: u32, width: u32, height: u32) -> GrayImage {
    let peak = (y..y + height)
        .flat_map(|yy| (x..x + width).map(move |xx| strength.get_pixel(xx, yy).0[0]))
        .max()
        .unwrap_or(0);
    let threshold = (u16::from(peak) * 40 / 100).max(18) as u8;
    GrayImage::from_fn(width, height, |xx, yy| {
        Luma([if strength.get_pixel(x + xx, y + yy).0[0] >= threshold {
            0
        } else {
            255
        }])
    })
}

fn visual_key(patch: &GrayImage) -> String {
    let mut hash = DefaultHasher::new();
    (patch.width(), patch.height(), patch.as_raw()).hash(&mut hash);
    format!("{:016x}", hash.finish())
}

impl PickupLogReader {
    pub fn read(&mut self, frame: &Frame) -> Value {
        if !(180..=720).contains(&frame.width) || !(40..=340).contains(&frame.height) {
            return json!({"valid":false,"state":"unreadable","partial":true,"lines":[]});
        }
        let Some(image) = RgbaImage::from_raw(frame.width, frame.height, frame.rgba.clone()) else {
            return json!({"valid":false,"state":"unreadable","partial":true,"lines":[]});
        };
        let mut white = GrayImage::new(frame.width, frame.height);
        let mut yellow = GrayImage::new(frame.width, frame.height);
        let mut strength = GrayImage::new(frame.width, frame.height);
        for y in 0..frame.height {
            for x in 0..frame.width {
                let (a, b) = ink_components(&image, x, y);
                white.put_pixel(x, y, Luma([a]));
                yellow.put_pixel(x, y, Luma([b]));
                strength.put_pixel(x, y, Luma([a.max(b)]));
            }
        }
        let mut rows = Vec::new();
        let mut calls = 0;
        let mut unresolved = false;
        let mut candidates = 0;
        let mut budget_exhausted = false;
        for (top, bottom) in bands(&strength)
            .into_iter()
            .rev()
            .take(24)
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
        {
            let edge = frame.width.saturating_sub(96);
            let mut white_pixels = (top..bottom)
                .flat_map(|y| (edge..frame.width).map(move |x| (x, y)))
                .filter(|&(x, y)| white.get_pixel(x, y).0[0] != 0)
                .count();
            let mut yellow_pixels = (top..bottom)
                .flat_map(|y| (edge..frame.width).map(move |x| (x, y)))
                .filter(|&(x, y)| yellow.get_pixel(x, y).0[0] != 0)
                .count();
            if white_pixels + yellow_pixels < 8 {
                white_pixels = (top..bottom)
                    .flat_map(|y| (0..frame.width).map(move |x| (x, y)))
                    .filter(|&(x, y)| white.get_pixel(x, y).0[0] != 0)
                    .count();
                yellow_pixels = (top..bottom)
                    .flat_map(|y| (0..frame.width).map(move |x| (x, y)))
                    .filter(|&(x, y)| yellow.get_pixel(x, y).0[0] != 0)
                    .count();
            }
            let line_strength = if white_pixels >= 8 && white_pixels >= yellow_pixels {
                &white
            } else {
                &yellow
            };
            let columns = (0..frame.width)
                .filter(|&x| (top..bottom).any(|y| line_strength.get_pixel(x, y).0[0] != 0))
                .collect::<Vec<_>>();
            if columns.is_empty() {
                continue;
            }
            let mut starts = vec![columns[0]];
            for pair in columns.windows(2) {
                if pair[1] - pair[0] >= 15 {
                    starts.push(pair[1]);
                }
            }
            let right = *columns.last().unwrap() + 1;
            let mut found = None;
            let mut evidence = None;
            let mut plausible = false;
            for left in starts.into_iter().rev() {
                let width = right - left;
                if !(80..=600).contains(&width) {
                    continue;
                }
                plausible = true;
                let patch = normalized_patch(line_strength, left, top, width, bottom - top);
                let visual = visual_key(&patch);
                if right + 24 >= frame.width {
                    evidence = Some(
                        json!({"key":format!("visual:{visual}"),"mesos":null,"kind":"unknown",
                        "rect":{"x":left,"y":top,"width":width,"height":bottom-top},"visualKey":visual}),
                    );
                }
                let key = (patch.width(), patch.height(), patch.as_raw().clone());
                let value = if let Some(value) = self.cache.get(&key) {
                    value.clone()
                } else {
                    if calls >= MAX_OCR_CALLS {
                        budget_exhausted = true;
                        break;
                    }
                    calls += 1;
                    let value = crate::text::read(&patch).and_then(|text| message(&text));
                    if self.cache.len() >= MAX_CACHE_ENTRIES {
                        self.cache.clear();
                    }
                    self.cache.insert(key, value.clone());
                    value
                };
                if let Some(value) = value {
                    found = Some(
                        json!({"key":value.key,"mesos":value.mesos,"kind":value.kind,
                        "rect":{"x":left,"y":top,"width":width,"height":bottom-top},
                        "visualKey":visual}),
                    );
                    break;
                }
            }
            if plausible {
                candidates += 1;
            }
            if let Some(value) = found {
                rows.push(value);
            } else if plausible {
                unresolved = true;
                if let Some(value) = evidence {
                    rows.push(value);
                }
            }
            if budget_exhausted {
                unresolved = true;
                break;
            }
        }
        let state = if rows.iter().any(|row| row["kind"] != "unknown") {
            "readable"
        } else if candidates > 0 {
            "unreadable"
        } else {
            "empty"
        };
        json!({"valid":true,"state":state,"partial":unresolved,"lines":rows})
    }
}

#[cfg(test)]
mod tests {
    use super::{message, normalized_patch, visual_key};
    use image::{GrayImage, Luma, Rgba, RgbaImage};

    #[test]
    fn white_glyphs_keep_exact_shape_while_fading_over_colored_scenery() {
        let shape = |x, y| x % 5 == 2 && (3..13).contains(&y);
        let render = |alpha: u16| {
            let image = RgbaImage::from_fn(40, 16, |x, y| {
                let background = if x < 20 { [120u16, 70, 0] } else { [0, 0, 0] };
                let mut pixel = [0, 0, 0, 255];
                for channel in 0..3 {
                    pixel[channel] = if shape(x, y) {
                        ((255 * alpha + background[channel] * (255 - alpha)) / 255) as u8
                    } else {
                        background[channel] as u8
                    };
                }
                Rgba(pixel)
            });
            let ink =
                GrayImage::from_fn(40, 16, |x, y| Luma([super::ink_components(&image, x, y).0]));
            normalized_patch(&ink, 0, 0, 40, 16)
        };
        let bright = render(190);
        let faded = render(40);
        assert_eq!(bright, faded);
        for (x, y, pixel) in faded.enumerate_pixels() {
            assert_eq!(pixel.0[0] == 0, shape(x, y));
        }
    }

    #[test]
    fn counts_only_complete_literal_pickup_lines() {
        let ordinary = message("You have gained mesos (+29).").unwrap();
        assert_eq!(ordinary.mesos, Some(29));
        assert_eq!(ordinary.kind, "meso");
        assert_eq!(ordinary.key, "mesos:29");
        assert_eq!(
            message("You have gained mesos (+2,500,000)").unwrap().mesos,
            Some(2_500_000)
        );
        for text in [
            "29",
            "You have gained mesos (+2.5m)",
            "You have gained mesos (+2,50)",
            "Player: You have gained mesos (+29)",
            "You have gained mesos (-29)",
            "You have gained mesos (+2147483648)",
        ] {
            assert_eq!(message(text), None, "{text}");
        }
    }

    #[test]
    fn classic_exp_party_and_item_receipts_are_non_currency_anchors() {
        for (text, kind) in [
            ("You received EXP (+23)", "exp"),
            ("You have gained experience (+150)", "exp"),
            ("Bonus EXP for PARTY (+2)", "party_exp"),
            ("Green Mushroo... x1 earned. (Etc)", "item"),
            ("Green Mushroom 1 earned. (Etc)", "item"),
        ] {
            let parsed = message(text).unwrap();
            assert_eq!(parsed.kind, kind);
            assert_eq!(parsed.mesos, None);
        }
        for text in [
            "You received EXP (+2.5m)",
            "Bonus EXP for PARTY (+1,00)",
            "Player: Green Mushroom x1 earned. (Etc)",
            "Green Mushroom x-1 earned. (Etc)",
        ] {
            assert_eq!(message(text), None, "{text}");
        }
    }

    #[test]
    fn normalized_visual_key_ignores_uniform_fading_and_crop_offset() {
        let bright = GrayImage::from_fn(12, 8, |x, y| {
            Luma([if x % 3 == 1 && y > 1 { 240 } else { 0 }])
        });
        let faded = GrayImage::from_fn(20, 12, |x, y| {
            Luma([
                if (4..16).contains(&x) && (2..10).contains(&y) && (x - 4) % 3 == 1 && y > 3 {
                    70
                } else {
                    0
                },
            ])
        });
        assert_eq!(
            visual_key(&normalized_patch(&bright, 0, 0, 12, 8)),
            visual_key(&normalized_patch(&faded, 4, 2, 12, 8))
        );
    }
}
