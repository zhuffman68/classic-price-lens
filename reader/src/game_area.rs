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
    pub footer: Rect,
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
            }).or_else(|| footer_span_across_description(image, lv, scale));
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
                    footer: Rect {
                        x: left,
                        y: lv.y.saturating_sub((7.0*ui_scale).round() as u32),
                        width: right-left,
                        height: bottom-lv.y.saturating_sub((7.0*ui_scale).round() as u32),
                    },
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
    let mut best = None;
    let from = lv.y.saturating_sub((9.0 * scale).ceil() as u32);
    let end = (lv.y + (3.0 * scale).ceil() as u32).min(image.height() - 1);
    let sample = (lv.x + (12.0 * scale).round() as u32).min(image.width() - 1);
    for y in from..=end {
        let Some((left, right)) = light_run(image, sample, y) else { continue };
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

fn footer_light(image: &RgbaImage, x: u32, y: u32) -> bool {
    let p = image.get_pixel(x, y).0;
    let low = p[..3].iter().min().unwrap();
    let high = p[..3].iter().max().unwrap();
    *low > 130 && *high - *low < 70
}

fn light_run(image: &RgbaImage, sample: u32, y: u32) -> Option<(u32, u32)> {
    if sample >= image.width() || !footer_light(image, sample, y) {
        return None;
    }
    let mut left = sample;
    let mut right = sample + 1;
    while left > 0 && footer_light(image, left - 1, y) {
        left -= 1;
    }
    while right < image.width() && footer_light(image, right, y) {
        right += 1;
    }
    Some((left, right))
}

/// Cold acquisition cannot use cached bounds when a description crosses the
/// footer. Require both real rim endpoints on repeated rows, a complete native
/// description frame/title marker inside the gap, and the independent caption.
/// Arbitrary covered/fragmented footers remain ineligible.
fn footer_span_across_description(image: &RgbaImage, lv: Rect, scale: f32) -> Option<(u32, u32)> {
    let from = lv.y.saturating_sub((9.0 * scale).ceil() as u32);
    let end = (lv.y + (3.0 * scale).ceil() as u32).min(image.height() - 1);
    let left_sample = lv.x + (12.0 * scale).round() as u32;
    let right_sample = lv.x + (786.0 * scale).round() as u32;
    let mut candidates: Vec<(u32, u32, u32, u32, u32, u32)> = Vec::new();
    for y in from..=end {
        let Some((left, gap_left)) = light_run(image, left_sample, y) else { continue };
        let Some((gap_right, right)) = light_run(image, right_sample, y) else { continue };
        if gap_right <= gap_left || right <= left {
            continue;
        }
        let width = (right - left) as f32 / scale;
        let gap = (gap_right - gap_left) as f32 / scale;
        if !(740.0..=840.0).contains(&width) || !(70.0..=700.0).contains(&gap)
            || left.abs_diff(lv.x) as f32 > 9.0 * scale
            || ((gap_left - left).min(right - gap_right) as f32) < 24.0 * scale
        {
            continue;
        }
        if let Some(candidate) = candidates.iter_mut().find(|c| {
            c.0.abs_diff(left) <= 2 && c.1.abs_diff(right) <= 2
                && c.2.abs_diff(gap_left) <= 2 && c.3.abs_diff(gap_right) <= 2
        }) {
            candidate.5 += 1;
        } else {
            candidates.push((left, right, gap_left, gap_right, y, 1));
        }
    }
    let mut found = None;
    for (left, right, gap_left, gap_right, y, rows) in candidates {
        if rows < 2 || !description_crosses_rim(image, gap_left, gap_right, y, scale) {
            continue;
        }
        let ui_scale = (right - left) as f32 / 798.0;
        let bottom = ((lv.y as f32 + 38.0 * ui_scale).round() as u32).min(image.height());
        let Some(area) = caption_bounds(image, left, right, bottom, ui_scale) else { continue };
        if !caption_still_present(image, area) {
            continue;
        }
        if found.is_some_and(|span| span != (left, right)) {
            return None;
        }
        found = Some((left, right));
    }
    found
}

// A translucent one-pixel gap can show a dark or bright background between the
// two matching dark frame strokes. This is used only with the other independent
// cold-acquisition proofs, never to relax ordinary tooltip/occlusion detection.
fn description_stroke(a: [u8; 4], b: [u8; 4], c: [u8; 4], tolerance: u8) -> bool {
    (0..3).all(|i| a[i] < 180 && c[i] < 180 && a[i].abs_diff(c[i]) <= tolerance)
        // A resampled single dark/light transition is not two frame strokes.
        // The middle gap must reverse contrast against both outer samples.
        && (0..3).any(|i| {
            let first=i16::from(b[i])-i16::from(a[i]);
            let second=i16::from(b[i])-i16::from(c[i]);
            (first>=18 && second>=18) || (first<=-18 && second<=-18)
        })
}

fn description_edge(image: &RgbaImage, x: u32, y: u32, scale: f32, horizontal: bool) -> bool {
    let outer=(2.0*scale).round().max(2.0) as u32;
    let middle=[scale.floor().max(1.0) as u32,scale.ceil().max(1.0) as u32];
    // Fractional resize interpolation blends the outer strokes with different
    // neighbours. Probe only the quantized positions inside one scaled pixel;
    // the caption/endpoints/title/body proofs stay independently mandatory.
    let tolerance=if (scale-1.0).abs()<0.1 {18} else {64};
    for phase in 0..scale.ceil().max(1.0) as u32 {
        let point=|delta:u32| if horizontal {(x,y+phase+delta)} else {(x+phase+delta,y)};
        let (end_x,end_y)=point(outer);
        if end_x>=image.width() || end_y>=image.height() {continue}
        let (a_x,a_y)=point(0);
        for offset in middle {
            let (b_x,b_y)=point(offset);
            if description_stroke(image.get_pixel(a_x,a_y).0,image.get_pixel(b_x,b_y).0,image.get_pixel(end_x,end_y).0,tolerance) {
                return true;
            }
        }
    }
    false
}

fn description_crosses_rim(image: &RgbaImage, left: u32, right: u32, rim_y: u32, scale: f32) -> bool {
    if left + 28 >= right || right > image.width() || rim_y < 70 {
        return false;
    }
    let frame_right = right.saturating_sub((3.0*scale).round().max(3.0) as u32);
    let top = rim_y.saturating_sub((460.0 * scale).ceil() as u32);
    let bottom = rim_y.saturating_sub((40.0 * scale).ceil() as u32);
    if bottom <= top { return false }
    let marker_left = left + 4;
    let marker_width = (28.0 * scale).ceil().clamp(12.0, 42.0) as u32;
    if marker_left + marker_width >= frame_right { return false }
    let markers = crate::tooltip_surface::dots_in(marker_width, bottom - top, |x, y| {
        let p = image.get_pixel(marker_left + x, top + y).0;
        [p[0], p[1], p[2]]
    });
    for marker in markers {
        let mx = marker_left + marker.x1;
        let my = top + marker.y0;
        let name_top = my.saturating_sub(4);
        let name_bottom = (top + marker.y1 + 4).min(image.height());
        let title_pixels = (name_top..name_bottom).flat_map(|y| (mx + 2..frame_right - 4).map(move |x| (x,y)))
            .filter(|&(x,y)| {
                let p = image.get_pixel(x,y).0;
                crate::tooltip_surface::title_light([p[0],p[1],p[2]]).is_some_and(|v|v>=150)
            }).take(16).count();
        if title_pixels < 16 { continue }
        let header_from = my.saturating_sub((24.0 * scale).ceil() as u32);
        let header_to = my.saturating_sub((5.0 * scale).floor() as u32);
        let header = (header_from..header_to).find(|&y| {
            let xs = (left + 5..frame_right - 4).step_by(6);
            let total = xs.clone().count();
            total >= 10 && xs.filter(|&x| description_edge(image,x,y,scale,true)).count() * 10 >= total * 7
        });
        let Some(header) = header else { continue };
        let ys = (header + 5..rim_y).step_by(6);
        let total = ys.clone().count();
        if total < 10 || ![left, frame_right].into_iter().all(|x| {
            ys.clone().filter(|&y| description_edge(image,x,y,scale,false)).count() * 10 >= total * 7
        }) { continue }
        let points = (header + 5..rim_y).step_by(7).flat_map(|y| (left + 5..frame_right - 4).step_by(11).map(move |x| (x,y)));
        let total = points.clone().count();
        let dark = points.filter(|&(x,y)| {
            let p=image.get_pixel(x,y).0;
            u32::from(p[0])*30+u32::from(p[1])*59+u32::from(p[2])*11 < 15000
        }).count();
        if total > 0 && dark * 10 >= total * 6 { return true }
    }
    false
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

#[cfg(test)]
mod tests {
    use super::*;
    use image::Rgba;

    fn fill_rect(image: &mut RgbaImage, x: u32, y: u32, w: u32, h: u32, p: [u8; 4]) {
        for row in y..y+h {
            for col in x..x+w {
                image.put_pixel(col,row,Rgba(p));
            }
        }
    }

    fn crossing_fixture() -> (RgbaImage, Rect) {
        let mut image = RgbaImage::from_pixel(1600,900,Rgba([55,48,43,255]));
        fill_rect(&mut image,120,90,960,600,[145,124,108,255]);
        fill_rect(&mut image,120,90,960,24,[40,48,59,255]);
        fill_rect(&mut image,200,646,800,5,[235,235,235,255]);
        let label=image::load_from_memory(include_bytes!("../../price_lens/resources/hud/level-label.png")).unwrap().into_rgba8();
        image::imageops::replace(&mut image,&label,201,652);
        // The level-number candidate independently leads to the exact LV image.
        fill_rect(&mut image,245,666,12,13,[255,136,0,255]);
        fill_rect(&mut image,500,450,243,240,[30,30,70,255]);
        for x in [500,740] {
            fill_rect(&mut image,x+1,450,1,240,[190,190,205,255]);
        }
        fill_rect(&mut image,500,451,243,1,[190,190,205,255]);
        for y in 465..470 {
            for x in 509..514 {
                if (x as i32-511).abs()+(y as i32-467).abs()<=2 {
                    image.put_pixel(x,y,Rgba([85,204,255,255]));
                }
            }
        }
        for x in (520..580).step_by(4) {
            fill_rect(&mut image,x,464,2,7,[235,235,235,255]);
        }
        (image,Rect{x:201,y:652,width:36,height:37})
    }

    #[test]
    fn writer_layout_receives_full_measured_footer_without_weakening_guards() {
        let (mut image,lv)=crossing_fixture();
        let mut locator=Locator::new();
        let located=locator.find(&image).expect("verified game");
        assert_eq!(located.footer.x,200);
        assert_eq!(located.footer.width,800);
        assert!(located.footer.y<lv.y);
        assert_eq!(located.footer.y+located.footer.height,located.area.y+located.area.height);
        assert_eq!(located.guards[1],lv);
        fill_rect(&mut image,900,646,100,5,[30,30,70,255]);
        assert_eq!(locator.find(&image).expect("retained proof").footer,located.footer);
        fill_rect(&mut image,lv.x,lv.y,lv.width,lv.height,[30,30,70,255]);
        assert!(locator.find(&image).is_none());
    }

    #[test]
    fn cold_locator_requires_description_caption_and_both_rim_endpoints() {
        let (image,lv)=crossing_fixture();
        assert!(footer_span(&image,lv,1.0).is_none());
        assert_eq!(footer_span_across_description(&image,lv,1.0),Some((200,1000)));
        let area=Locator::new().find(&image).expect("cold acquisition across native description").area;
        assert_eq!(area,Rect{x:120,y:90,width:960,height:600});

        let mut missing_right=image.clone();
        fill_rect(&mut missing_right,900,646,100,5,[30,30,70,255]);
        assert!(Locator::new().find(&missing_right).is_none());

        let mut missing_caption=image.clone();
        // Remove all upper flat runs, not merely the caption colour.
        for y in 0..290 {
            for x in 120..1080 {
                missing_caption.put_pixel(x,y,Rgba([((x*37+y*13)%256) as u8,20,40,255]));
            }
        }
        assert!(Locator::new().find(&missing_caption).is_none());

        let mut missing_level=image.clone();
        fill_rect(&mut missing_level,201,652,76,37,[30,30,70,255]);
        assert!(Locator::new().find(&missing_level).is_none());
    }

    #[test]
    fn cold_locator_rejects_plain_gaps_fake_markers_and_bright_panels() {
        let (image,lv)=crossing_fixture();
        for defect in ["marker","top","side","body","plain"] {
            let mut altered=image.clone();
            match defect {
                "marker"=>fill_rect(&mut altered,509,465,5,5,[30,30,70,255]),
                "top"=>fill_rect(&mut altered,500,450,243,3,[30,30,70,255]),
                "side"=>fill_rect(&mut altered,740,454,3,230,[30,30,70,255]),
                "body"=>fill_rect(&mut altered,504,480,232,162,[235,235,235,255]),
                "plain"=>fill_rect(&mut altered,500,450,243,240,[30,30,70,255]),
                _=>unreachable!(),
            }
            assert!(footer_span_across_description(&altered,lv,1.0).is_none(),"{defect}");
            assert!(Locator::new().find(&altered).is_none(),"{defect}");
        }
    }

    #[test]
    fn cold_description_proofs_follow_fractional_and_double_pixel_scales() {
        let (image,lv)=crossing_fixture();
        for scale in [1.25_f32,1.5,2.0] {
            for filter in [FilterType::Nearest,FilterType::Triangle] {
                let scaled=image::imageops::resize(&image,(image.width() as f32*scale).round() as u32,(image.height() as f32*scale).round() as u32,filter);
                let scaled_lv=Rect{x:(lv.x as f32*scale).round() as u32,y:(lv.y as f32*scale).round() as u32,width:(lv.width as f32*scale).round() as u32,height:(lv.height as f32*scale).round() as u32};
                assert!(footer_span(&scaled,scaled_lv,scale).is_none());
                assert!(footer_span_across_description(&scaled,scaled_lv,scale).is_some(),"{scale} {filter:?}");
                let area=Locator::new().find(&scaled).unwrap_or_else(||panic!("{scale} {filter:?}")).area;
                for (value,expected) in [(area.x,120.0*scale),(area.y,90.0*scale),(area.width,960.0*scale),(area.height,600.0*scale)] {
                    assert!(value.abs_diff(expected.round() as u32)<=4,"{scale} {filter:?}: {area:?}");
                }
                for defect in ["marker","top","plain"] {
                    let mut altered=image.clone();
                    match defect {
                        "marker"=>fill_rect(&mut altered,509,465,5,5,[30,30,70,255]),
                        "top"=>fill_rect(&mut altered,500,450,243,3,[30,30,70,255]),
                        "plain"=>fill_rect(&mut altered,500,450,243,240,[30,30,70,255]),
                        _=>unreachable!(),
                    }
                    let negative=image::imageops::resize(&altered,scaled.width(),scaled.height(),filter);
                    assert!(footer_span_across_description(&negative,scaled_lv,scale).is_none(),"{scale} {filter:?}: {defect}");
                }
            }
        }
    }

    #[test]
    fn warm_caption_and_level_guards_survive_description_after_cold_acquisition() {
        let (mut image,_)=crossing_fixture();
        let mut locator=Locator::new();
        let before=locator.find(&image).unwrap();
        // Cover the rim's right endpoint after acquisition. Only the existing
        // verified LV+caption path may retain bounds; a cold locator rejects it.
        fill_rect(&mut image,900,646,100,5,[30,30,70,255]);
        assert!(Locator::new().find(&image).is_none());
        assert_eq!(locator.find(&image).unwrap().area,before.area);
        fill_rect(&mut image,201,652,76,37,[30,30,70,255]);
        assert!(locator.find(&image).is_none());
    }
}
