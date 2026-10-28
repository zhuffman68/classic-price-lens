//! Locate the visible Classic client using pixels only, before any item OCR.
//! Static HUD references are cropped from Minerva's pinned public MIT fixtures.
use image::{RgbaImage, imageops::FilterType};
use serde::{Deserialize, Serialize};
use std::collections::VecDeque;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq)]
pub struct Rect {
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}

#[derive(Clone, Debug, Serialize)]
pub struct Located {
    pub area: Rect,
    pub guards: Vec<Rect>,
}

struct Blob {
    rect: Rect,
    count: u32,
}

pub struct Locator {
    level: RgbaImage,
    world: RgbaImage,
    corner: RgbaImage,
    last: Option<Located>,
    last_footer: Option<(u32,u32)>,
    last_scan: std::time::Instant,
}

impl Locator {
    pub fn new() -> Self {
        let decode = |data: &[u8]| {
            image::load_from_memory(data)
                .expect("bundled HUD reference")
                .into_rgba8()
        };
        Self {
            level: decode(include_bytes!(
                "../../price_lens/resources/hud/level-label.png"
            )),
            world: decode(include_bytes!(
                "../../price_lens/resources/hud/world-button.png"
            )),
            corner: decode(include_bytes!(
                "../../price_lens/resources/hud/map-left-edge.png"
            )),
            last: None,
            last_footer: None,
            last_scan: std::time::Instant::now(),
        }
    }

    pub fn find(&mut self, image: &RgbaImage) -> Option<Located> {
        let debug = std::env::var_os("CLASSIC_LENS_DEBUG_AREA").is_some();
        let previous = self.last.clone();
        let mut levels = Vec::new();
        if let Some(last) = &previous {
            if last.guards.len() == 2 && score(image, &self.level, last.guards[1]) < 24.0 {
                let lv = last.guards[1];
                levels.push((0.0, lv, lv.width as f32 / 36.0));
            }
        }
        let mut worlds = Vec::new();
        if levels.is_empty() || self.last_scan.elapsed().as_millis() > 1000 {
            self.last_scan = std::time::Instant::now();
            levels.clear();
            let blobs = orange_blobs(image);
            worlds = blobs
                .iter()
                .filter(|b| {
                    let r = b.rect;
                    (18..=110).contains(&r.width)
                        && (5..=40).contains(&r.height)
                        && (2.7..=4.3).contains(&(r.width as f32 / r.height as f32))
                        && score(image, &self.world, r) < 27.0
                })
                .map(|b| b.rect)
                .collect();
            for blob in &blobs {
                let r = blob.rect;
                if !(7..=42).contains(&r.height)
                    || !(5..=38).contains(&r.width)
                    || !(0.55..=1.15).contains(&(r.width as f32 / r.height as f32))
                    || blob.count * 100 < r.width * r.height * 35
                {
                    continue;
                }
                let estimate = r.height as f32 / 13.0;
                let mut best = (f32::MAX, r, estimate);
                for step in -5..=3 {
                    let scale = estimate + step as f32 * 0.02;
                    if scale < 0.5 {
                        continue;
                    }
                    let w = (36.0 * scale).round() as u32;
                    let h = (37.0 * scale).round() as u32;
                    let reference =
                        image::imageops::resize(&self.level, w, h, FilterType::Triangle);
                    let px = r.x as i32 - (44.0 * scale).round() as i32;
                    let py = r.y as i32 - (14.0 * scale).round() as i32;
                    for dy in -3..=3 {
                        for dx in -3..=3 {
                            if px + dx < 0 || py + dy < 0 {
                                continue;
                            }
                            let candidate = Rect {
                                x: (px + dx) as u32,
                                y: (py + dy) as u32,
                                width: w,
                                height: h,
                            };
                            let value = score_prepared(image, &reference, candidate);
                            if value < best.0 {
                                best = (value, candidate, scale);
                            }
                        }
                    }
                }
                if debug && best.0 < 30.0 {
                    eprintln!("Status bar: {best:?}");
                }
                if best.0 < 24.0
                    && !levels.iter().any(|(_, r, _): &(f32, Rect, f32)| {
                        r.x.abs_diff(best.1.x) < 8 && r.y.abs_diff(best.1.y) < 8
                    })
                {
                    levels.push(best);
                }
            }
        }
        let mut found: Vec<Located> = Vec::new();
        let mut found_footer = None;
        for (_, lv, scale) in levels {
            // A tall item description can cross the white footer rim. The
            // already-proven bounds remain usable only while the independent
            // LV anchor and OS caption are still visible at those coordinates.
            let span=footer_span(image, lv, scale).or_else(|| {
                let last=previous.as_ref()?;
                let old=*last.guards.get(1)?;
                if old.x.abs_diff(lv.x)>3 || old.y.abs_diff(lv.y)>3
                    || score(image,&self.level,old)>=24.0 || !caption_still_present(image,last.area) {return None}
                self.last_footer
            });
            let Some((left, right)) = span else {
                continue;
            };
            let ui_scale = (right - left) as f32 / 798.0;
            let bottom = ((lv.y as f32 + 38.0 * ui_scale).round() as u32).min(image.height());
            let mut area = previous
                .as_ref()
                .and_then(|last| {
                    let r = last.area;
                    if r.y > 0
                        && bottom.abs_diff(r.y + r.height) <= 3
                        && caption_still_present(image, r)
                    {
                        Some(r)
                    } else {
                        None
                    }
                })
                .or_else(|| caption_bounds(image, left, right, bottom, ui_scale));
            // A borderless full-display view can be bootstrapped from the HUD at
            // the display edges. A movable minimap never sets windowed bounds.
            if area.is_none()
                && bottom.abs_diff(image.height()) <= 8
                && (left + right).abs_diff(image.width()) <= 16
            {
                if previous.as_ref().is_some_and(|last| {
                    last.area.x == 0
                        && last.area.y == 0
                        && last.area.width == image.width()
                        && last.area.height == image.height()
                }) {
                    area = Some(Rect {
                        x: 0,
                        y: 0,
                        width: image.width(),
                        height: image.height(),
                    });
                } else {
                    for world in &worlds {
                        let ws = world.width as f32 / 34.5;
                        if (world.y as f32 - 7.0 * ws).abs() > 6.0 {
                            continue;
                        }
                        let cw = (self.corner.width() as f32 * ws / 1.56).round().max(4.0) as u32;
                        let ch = (self.corner.height() as f32 * ws / 1.56).round().max(6.0) as u32;
                        let edge_y = world.y + world.height + (2.0 * ws / 1.56).round() as u32;
                        let reference =
                            image::imageops::resize(&self.corner, cw, ch, FilterType::Triangle);
                        if (0..=5).any(|x| {
                            score_prepared(
                                image,
                                &reference,
                                Rect {
                                    x,
                                    y: edge_y,
                                    width: cw,
                                    height: ch,
                                },
                            ) < 25.0
                        }) {
                            area = Some(Rect {
                                x: 0,
                                y: 0,
                                width: image.width(),
                                height: image.height(),
                            });
                            break;
                        }
                    }
                }
            }
            let Some(area) = area else {
                continue;
            };
            // Focus changes recolour the OS caption. Only static game HUD pixels
            // guard the current coordinates between locator reads.
            let guard = Rect {
                x: lv.x,
                y: lv.y + lv.height.saturating_sub(3),
                width: lv.width,
                height: 3,
            };
            if !found
                .iter()
                .any(|f| f.area.x.abs_diff(area.x) < 8 && f.area.y.abs_diff(area.y) < 8)
            {
                found.push(Located {
                    area,
                    guards: vec![guard, lv],
                });
                found_footer=Some((left,right));
            }
        }
        self.last = if found.len() == 1 { found.pop() } else { None };
        self.last_footer=if self.last.is_some() {found_footer} else {None};
        if debug {
            eprintln!("Game area: {:?}", self.last.as_ref().map(|l| l.area));
        }
        self.last.clone()
    }
}

fn caption_still_present(image: &RgbaImage, r: Rect) -> bool {
    if r.x + r.width > image.width() || r.y + 1 >= image.height() {
        return false;
    }
    let sample = image.get_pixel(r.x + r.width / 4, r.y + 1).0;
    for x in [
        r.x.checked_sub(1),
        (r.x + r.width < image.width()).then_some(r.x + r.width),
    ]
    .into_iter()
    .flatten()
    {
        let outside = image.get_pixel(x, r.y + 1).0;
        if (0..3).all(|c| outside[c].abs_diff(sample[c]) < 12) {
            return false;
        }
    }
    // Compare the caption with itself, allowing active/inactive colours.
    (1..8).all(|i| {
        let p = image.get_pixel(r.x + r.width * i / 9, r.y + 1).0;
        (0..3).all(|c| p[c].abs_diff(sample[c]) < 12)
    })
}

fn caption_bounds(
    image: &RgbaImage,
    bar_left: u32,
    bar_right: u32,
    bottom: u32,
    scale: f32,
) -> Option<Rect> {
    if bottom < 400 {
        return None;
    }
    let centre = (bar_left + bar_right) / 2;
    let seed = centre.saturating_sub((bar_right - bar_left) / 4);
    // Mild compositor/video colour variation must not split a flat caption.
    // Width, symmetry, multiple rows and the independent HUD remain required.
    let near = |a: [u8; 4], b: [u8; 4]| (0..3).all(|i| a[i].abs_diff(b[i]) <= 12);
    let mut groups: Vec<(u32, u32, u32, u32, u32)> = Vec::new();
    for y in 0..bottom - 400 {
        let color = image.get_pixel(seed, y).0;
        let mut left = seed;
        let mut right = seed + 1;
        while left > 0 && near(image.get_pixel(left - 1, y).0, color) {
            left -= 1;
        }
        while right < image.width() && near(image.get_pixel(right, y).0, color) {
            right += 1;
        }
        if right - left < (bar_right - bar_left).saturating_sub((8.0 * scale).round() as u32)
            || (left + right).abs_diff(centre * 2) as f32 > 20.0 * scale
            || left > bar_left + 4
            || right + 4 < bar_right
        {
            continue;
        }
        if let Some(group) = groups.iter_mut().rev().find(|g| {
            y - g.3 <= (28.0 * scale) as u32
                && (g.0.abs_diff(left) as f32) < 24.0 * scale
                && (g.1.abs_diff(right) as f32) < 24.0 * scale
        }) {
            group.0 = group.0.min(left);
            group.1 = group.1.max(right);
            group.3 = y;
            group.4 += 1;
        } else {
            groups.push((left, right, y, y, 1));
        }
    }
    groups
        .into_iter()
        .filter(|g| g.4 >= 4 && g.3 - g.2 >= 8)
        .min_by_key(|g| (g.1 - g.0, g.2))
        .map(|g| Rect {
            x: g.0,
            y: g.2,
            width: g.1 - g.0,
            height: bottom - g.2,
        })
}

fn footer_span(image: &RgbaImage, lv: Rect, scale: f32) -> Option<(u32, u32)> {
    let light = |x, y| {
        let p = image.get_pixel(x, y).0;
        let low = p[..3].iter().min().unwrap();
        let high = p[..3].iter().max().unwrap();
        *low > 130 && *high - *low < 70
    };
    let mut best = None;
    let from = lv.y.saturating_sub((9.0 * scale).ceil() as u32);
    let end = (lv.y + (3.0 * scale).ceil() as u32).min(image.height() - 1);
    let sample = (lv.x + (12.0 * scale).round() as u32).min(image.width() - 1);
    for y in from..=end {
        if !light(sample, y) {
            continue;
        }
        let mut left = sample;
        let mut right = sample + 1;
        while left > 0 && light(left - 1, y) {
            left -= 1;
        }
        while right < image.width() && light(right, y) {
            right += 1;
        }
        let width = (right - left) as f32 / scale;
        if !(740.0..=840.0).contains(&width) || left.abs_diff(lv.x) as f32 > 9.0 * scale {
            continue;
        }
        if best.is_none_or(|(a, b)| right - left > b - a) {
            best = Some((left, right));
        }
    }
    best
}

fn score(image: &RgbaImage, reference: &RgbaImage, r: Rect) -> f32 {
    if r.width == 0
        || r.height == 0
        || r.x + r.width > image.width()
        || r.y + r.height > image.height()
    {
        return f32::MAX;
    }
    let resized = image::imageops::resize(reference, r.width, r.height, FilterType::Triangle);
    score_prepared(image, &resized, r)
}

fn score_prepared(image: &RgbaImage, resized: &RgbaImage, r: Rect) -> f32 {
    if r.width == 0
        || r.height == 0
        || r.x + r.width > image.width()
        || r.y + r.height > image.height()
    {
        return f32::MAX;
    }
    let mut coarse = 0.0;
    let mut samples = 0;
    for y in (0..r.height).step_by(4) {
        for x in (0..r.width).step_by(4) {
            let p = image.get_pixel(r.x + x, r.y + y).0;
            let q = resized.get_pixel(x, y).0;
            for c in 0..3 {
                coarse += (p[c] as f32 - q[c] as f32).abs();
                samples += 1;
            }
        }
    }
    if coarse / samples.max(1) as f32 > 50.0 {
        return f32::MAX;
    }
    let mut error = 0.0;
    let mut light = 0.0;
    let mut base = 0.0;
    // Allow uniform screenshot/capture brightness differences.
    for y in (0..r.height).step_by(2) {
        for x in (0..r.width).step_by(2) {
            let p = image.get_pixel(r.x + x, r.y + y).0;
            let q = resized.get_pixel(x, y).0;
            light += p[..3].iter().map(|v| *v as f32).sum::<f32>();
            base += q[..3].iter().map(|v| *v as f32).sum::<f32>();
        }
    }
    let brightness = (light / base.max(1.0)).clamp(0.75, 1.25);
    for y in 0..r.height {
        for x in 0..r.width {
            let p = image.get_pixel(r.x + x, r.y + y).0;
            let q = resized.get_pixel(x, y).0;
            for channel in 0..3 {
                error += (p[channel] as f32 - q[channel] as f32 * brightness).abs();
            }
        }
    }
    error / (r.width * r.height * 3) as f32
}

fn orange_blobs(image: &RgbaImage) -> Vec<Blob> {
    let (w, h) = image.dimensions();
    let mut mask: Vec<u8> = image
        .pixels()
        .map(|p| {
            let [r, g, b, _] = p.0.map(u32::from);
            u8::from(r >= 150 && 45 * r <= 100 * g && 100 * g <= 84 * r && 100 * b <= 25 * r)
        })
        .collect();
    let mut result = Vec::new();
    let mut queue = VecDeque::new();
    for index in 0..mask.len() {
        if mask[index] == 0 {
            continue;
        }
        mask[index] = 0;
        queue.push_back(index);
        let mut x0 = index as u32 % w;
        let mut x1 = x0;
        let mut y0 = index as u32 / w;
        let mut y1 = y0;
        let mut count = 0;
        while let Some(i) = queue.pop_front() {
            let x = i as u32 % w;
            let y = i as u32 / w;
            x0 = x0.min(x);
            x1 = x1.max(x);
            y0 = y0.min(y);
            y1 = y1.max(y);
            count += 1;
            for (valid, next) in [
                (x > 0, i.wrapping_sub(1)),
                (x + 1 < w, i + 1),
                (y > 0, i.wrapping_sub(w as usize)),
                (y + 1 < h, i + w as usize),
            ] {
                if valid && mask[next] != 0 {
                    mask[next] = 0;
                    queue.push_back(next);
                }
            }
        }
        if count >= 20 {
            result.push(Blob {
                rect: Rect {
                    x: x0,
                    y: y0,
                    width: x1 - x0 + 1,
                    height: y1 - y0 + 1,
                },
                count,
            });
        }
    }
    result
}
