//! Cash-item descriptions have centered, sometimes wrapped titles and no marker.
//! Require both repeated native frame edges; OCR only the centered header lines.
use crate::tooltip_surface::{horizontal_rim, rgb, rim};
use image::{GrayImage, Luma};
use minerva_core::{Frame, ItemCapture, ItemTooltip, ScreenRect};
use std::collections::VecDeque;

#[derive(Clone, Copy)]
struct Edge {
    x: u32,
    top: u32,
    bottom: u32,
}

fn edges(frame: &Frame) -> Vec<Edge> {
    let mut result = Vec::new();
    for x in 0..frame.width.saturating_sub(2) {
        let (mut first, mut last, mut hits, mut gap) = (0, 0, 0, 0);
        for y in (0..frame.height + 9).step_by(3) {
            if y < frame.height && rim(frame, x, y) {
                if hits == 0 {
                    first = y
                }
                hits += 1;
                last = y;
                gap = 0;
            } else {
                gap += 1
            }
            if gap > 2 && hits > 0 {
                if last - first >= 80 && hits * 5 >= (1 + (last - first) / 3) * 3 {
                    result.push(Edge {
                        x,
                        top: first,
                        bottom: last,
                    })
                }
                hits = 0;
            }
        }
    }
    result
}

fn ink(frame: &Frame, x: u32, y: u32) -> u8 {
    let [r, g, b] = rgb(frame, x, y).map(i32::from);
    if (r - g).abs() > 55 || b - r > 100 {
        return 255;
    }
    let light = (r * 30 + g * 59 + b * 11) / 100;
    (255 - ((light - 130) * 255 / 90).clamp(0, 255)) as u8
}

#[derive(Default)]
pub struct CenteredTitles {
    cache: VecDeque<(Vec<u8>, Option<String>)>,
}

impl CenteredTitles {
    pub fn read(&mut self, capture: &ItemCapture) -> Option<ItemTooltip> {
        let frame = &capture.frame;
        let edges = edges(frame);
        let mut panels = Vec::new();
        for left in &edges {
            if let Some(right) = edges
                .iter()
                .filter(|right| {
                    right.x >= left.x + 140
                        && right.x <= left.x + 740
                        && right
                            .bottom
                            .min(left.bottom)
                            .saturating_sub(right.top.max(left.top))
                            >= 80
                })
                .min_by_key(|right| right.x)
            {
                let dx = i64::from((left.x + right.x) / 2) + i64::from(capture.origin.x)
                    - i64::from(capture.pointer.x);
                let dy = i64::from(left.top) + i64::from(capture.origin.y)
                    - i64::from(capture.pointer.y);
                panels.push((dx * dx + dy * dy, *left, *right));
            }
        }
        panels.sort_by_key(|p| p.0);
        for (_, left, right) in panels.into_iter().take(4) {
            let (x0, x1) = (left.x + 8, right.x.saturating_sub(6));
            let edge_top = left.top.min(right.top);
            let columns = (x0..x1).step_by(6);
            let cap = (edge_top.saturating_sub(96)
                ..=(edge_top + 6).min(frame.height.saturating_sub(3)))
                .find(|&y| {
                    columns
                        .clone()
                        .filter(|&x| horizontal_rim(frame, x, y))
                        .count()
                        * 100
                        >= columns.clone().count() * 55
                });
            let Some(cap) = cap else { continue };
            let (top, bottom) = (cap + 5, (cap + 62).min(frame.height).min(left.bottom));
            let mut lines = Vec::new();
            let mut start = None;
            for y in top..=bottom {
                let count = if y < bottom {
                    (x0..x1).filter(|&x| ink(frame, x, y) < 150).count()
                } else {
                    0
                };
                if count >= 1 {
                    start.get_or_insert(y);
                } else if let Some(first) = start.take() {
                    if (8..=24).contains(&(y - first)) {
                        lines.push((first, y))
                    }
                }
            }
            if lines.is_empty() || lines[0].0 > cap + 20 {
                continue;
            }
            let mut titles = Vec::new();
            for (y0, y1) in lines.into_iter().take(3) {
                if titles.last().is_some_and(|&(_, end)| y0 - end > 8) {
                    break;
                }
                let columns: Vec<_> = (x0..x1)
                    .filter(|&x| (y0..y1).any(|y| ink(frame, x, y) < 150))
                    .collect();
                let (Some(&first), Some(&last)) = (columns.first(), columns.last()) else {
                    break;
                };
                // A left-aligned stat/icon/body line is not a centered item name.
                if last - first < 40
                    || ((first + last) as i32 - (left.x + right.x) as i32).abs() > 30
                {
                    break;
                }
                titles.push((y0, y1));
            }
            if titles.is_empty() {
                continue;
            }
            let top = titles[0].0;
            let bottom = titles.last().unwrap().1;
            let mut key = Vec::new();
            key.extend_from_slice(&(x1 - x0).to_le_bytes());
            key.extend_from_slice(&(bottom - top).to_le_bytes());
            for &(first, last) in &titles {
                key.extend_from_slice(&(first - top).to_le_bytes());
                key.extend_from_slice(&(last - top).to_le_bytes())
            }
            key.extend((top..bottom).flat_map(|y| (x0..x1).map(move |x| ink(frame, x, y))));
            let name = if let Some((_, name)) = self.cache.iter().find(|(pixels, _)| *pixels == key)
            {
                name.clone()
            } else {
                let mut words = Vec::new();
                for &(y0, y1) in &titles {
                    let image = GrayImage::from_fn(x1 - x0, y1 - y0, |x, y| {
                        Luma([ink(frame, x0 + x, y0 + y)])
                    });
                    if let Some(line) = crate::text::read(&image) {
                        words.push(line)
                    } else {
                        words.clear();
                        break;
                    }
                }
                let name = (!words.is_empty()).then(|| words.join(" "));
                if self.cache.len() >= 8 {
                    self.cache.pop_front();
                }
                self.cache.push_back((key, name.clone()));
                name
            };
            if let Some(name) = name {
                return Some(ItemTooltip::Found {
                    area: ScreenRect {
                        x: x0 as i32 + capture.origin.x,
                        y: top as i32 + capture.origin.y,
                        width: x1 - x0,
                        height: bottom - top,
                    },
                    name: Some(name),
                });
            }
        }
        None
    }
}
