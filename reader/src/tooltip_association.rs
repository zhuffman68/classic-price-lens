//! Bind a fitted native comparison pair to its captured inventory source.
//! No names, market data, game state or input are used to choose the panel.
use crate::tooltip_surface::{Dot, rgb, title_light};
use minerva_core::{Frame, ItemCapture};
use serde_json::{Value, json};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct BoxRect {
    pub x: u32,
    pub y: u32,
    pub w: u32,
    pub h: u32,
}
impl BoxRect {
    fn right(self) -> u32 {
        self.x + self.w
    }
    fn bottom(self) -> u32 {
        self.y + self.h
    }
    fn contains(self, x: i32, y: i32) -> bool {
        x >= self.x as i32
            && y >= self.y as i32
            && x < (self.right()) as i32
            && y < (self.bottom()) as i32
    }
    fn global(self, c: &ItemCapture) -> Value {
        json!({"x":i64::from(self.x)+i64::from(c.origin.x),"y":i64::from(self.y)+i64::from(c.origin.y),"width":self.w,"height":self.h})
    }
}
#[derive(Clone)]
struct Inventory {
    rect: BoxRect,
    tab: u32,
    scale: f32,
    guard: Vec<u8>,
}
#[derive(Clone, Copy)]
struct Panel {
    rect: BoxRect,
    cap: bool,
}
#[derive(Clone, Copy)]
struct PairBinding {
    source: BoxRect,
    scope: (i32, i32, u32, u32),
    panels: [Panel; 2],
    scale: f32,
}

pub struct Association {
    pub panel: Option<BoxRect>,
    pub rejected: bool,
    pub metadata: Value,
}
#[derive(Default)]
pub struct Selector {
    inventory: Option<Inventory>,
    bound_source: Option<(BoxRect, (i32, i32, u32, u32))>,
    pair: Option<PairBinding>,
}

fn pink(p: [u8; 3]) -> bool {
    p[0] >= 180 && p[0].saturating_sub(p[1]) >= 35 && p[1].abs_diff(p[2]) < 55 && p[2] >= 60
}
fn header_guard(frame: &Frame, r: BoxRect, s: f32) -> Vec<u8> {
    let h = (45.0 * s).round() as u32;
    (r.y..(r.y + h).min(frame.height))
        .flat_map(|y| (r.x..r.right()).flat_map(move |x| rgb(frame, x, y)))
        .collect()
}
fn count(
    frame: &Frame,
    x: u32,
    y: u32,
    w: u32,
    h: u32,
    predicate: impl Fn([u8; 3]) -> bool,
) -> usize {
    (y..(y + h).min(frame.height))
        .flat_map(|row| (x..(x + w).min(frame.width)).map(move |col| (col, row)))
        .filter(|&(col, row)| predicate(rgb(frame, col, row)))
        .count()
}
fn source(
    frame: &Frame,
    px: i32,
    py: i32,
    old: Option<&Inventory>,
    scale_hint: Option<f32>,
) -> Option<Inventory> {
    if let Some(old) = old {
        if old.rect.right() <= frame.width
            && old.rect.bottom() <= frame.height
            && old.rect.contains(px, py)
            && header_guard(frame, old.rect, old.scale) == old.guard
        {
            return Some(old.clone());
        }
    }
    // This correction concerns a source close to the right game edge. Other
    // layouts keep the normal single/linked/equipped reader path.
    if px < 0 || py < 0 || px as u32 >= frame.width || py as u32 >= frame.height
        || frame.width.saturating_sub(px as u32) > 480 {
        return None;
    }
    let x0 = (px as u32).saturating_sub(440);
    let x1 = ((px as u32) + 440).min(frame.width);
    let y0 = (py as u32).saturating_sub(640);
    let y1 = (py as u32).min(frame.height);
    let w = x1 - x0;
    let h = y1 - y0;
    if w == 0 || h == 0 {
        return None;
    }
    let mut mask: Vec<u8> = (0..w * h)
        .map(|i| u8::from(pink(rgb(frame, x0 + i % w, y0 + i / w))))
        .collect();
    let mut candidates = Vec::new();
    let mut queue = Vec::new();
    for start in 0..mask.len() {
        if mask[start] == 0 {
            continue;
        }
        mask[start] = 0;
        queue.push(start);
        let (mut a, mut b, mut top, mut bottom, mut n) = (w, 0, h, 0, 0);
        while let Some(i) = queue.pop() {
            let x = i as u32 % w;
            let y = i as u32 / w;
            a = a.min(x);
            b = b.max(x + 1);
            top = top.min(y);
            bottom = bottom.max(y + 1);
            n += 1;
            for next in [
                x.checked_sub(1).map(|_| i - 1),
                (x + 1 < w).then_some(i + 1),
                y.checked_sub(1).map(|_| i - w as usize),
                (y + 1 < h).then_some(i + w as usize),
            ]
            .into_iter()
            .flatten()
            {
                if mask[next] != 0 {
                    mask[next] = 0;
                    queue.push(next)
                }
            }
        }
        let bw = b - a;
        let bh = bottom - top;
        if !(18..=62).contains(&bw) || !(11..=36).contains(&bh) || n * 3 < (bw * bh) as usize {
            continue;
        }
        // A proven HUD scale avoids treating antialiased widget-edge pixels as
        // a change in scale. Manual frame reads can still use the tab geometry.
        let s = scale_hint
            .filter(|s| (0.65..=2.1).contains(s))
            .unwrap_or(bh as f32 / 17.0);
        if ((bw as f32) / (29.0 * s) - 1.0).abs() > 0.18 {
            continue;
        }
        for tab in [0_u32, 4] {
            let dx = ((6.0 + 33.0 * tab as f32) * s).round() as u32;
            let dy = (23.0 * s).round() as u32;
            if x0 + a < dx || y0 + top < dy {
                continue;
            }
            let r = BoxRect {
                x: x0 + a - dx,
                y: y0 + top - dy,
                w: (207.0 * s).round() as u32,
                h: (285.0 * s).round() as u32,
            };
            if r.right() > frame.width
                || r.bottom() > frame.height
                || !r.contains(px, py)
                || frame.width - r.right() > (24.0 * s).ceil() as u32
            {
                continue;
            }
            let at = |x: f32, y: f32| {
                rgb(
                    frame,
                    r.x + (x * s).round() as u32,
                    r.y + (y * s).round() as u32,
                )
            };
            if ![20.0, 80.0, 135.0].into_iter().all(|x| {
                let p = at(x, 4.0);
                p.iter().all(|v| *v >= 210)
                    && p.iter().max().unwrap() - p.iter().min().unwrap() < 25
            }) {
                continue;
            }
            let mut buttons = true;
            for (cx, blue) in [(168.0, false), (181.0, false), (194.0, true)] {
                let size = (8.0 * s).round().max(4.0) as u32;
                let hits = count(
                    frame,
                    r.x + ((cx - 4.0) * s).round() as u32,
                    r.y + (5.0 * s).round() as u32,
                    size,
                    (10.0 * s).round() as u32,
                    |p| {
                        if blue {
                            p[2] >= 140
                                && p[1] >= 100
                                && p[0] <= 150
                                && p[1].saturating_sub(p[0]) >= 40
                        } else {
                            p[0] >= 150
                                && p[0].saturating_sub(p[1]) >= 45
                                && p[0].saturating_sub(p[2]) >= 35
                        }
                    },
                );
                buttons &= hits >= ((8.0 * s * s).round() as usize).max(4);
            }
            if !buttons {
                continue;
            }
            if !(0..6).filter(|i| *i != tab).all(|i| {
                let p = at(9.0 + 33.0 * i as f32, 29.0);
                p.iter().max().unwrap() - p.iter().min().unwrap() < 35
            }) {
                continue;
            }
            let ink = count(
                frame,
                r.x + (7.0 * s).round() as u32,
                r.y + (6.0 * s).round() as u32,
                (125.0 * s).round() as u32,
                (11.0 * s).round() as u32,
                |p| p.iter().all(|v| *v < 100),
            );
            if ink < ((30.0 * s * s).round() as usize).max(12) {
                continue;
            }
            candidates.push(Inventory {
                rect: r,
                tab,
                scale: s,
                guard: header_guard(frame, r, s),
            });
        }
    }
    candidates.sort_by_key(|s| (s.rect.x, s.rect.y));
    candidates.dedup_by_key(|s| (s.rect.x, s.rect.y));
    if candidates.len() == 1 {
        candidates.pop()
    } else {
        None
    }
}

fn edge(frame: &Frame, x: u32, y: u32, s: f32, horizontal: bool) -> bool {
    let outer = (2.0 * s).round().max(2.0) as u32;
    // At fractional scale the last dark stroke also blends with the bright
    // inventory outside the frame. A real middle contrast reversal remains
    // required; a monotone edge cannot satisfy this wider colour tolerance.
    let tolerance = if (s - 1.0).abs() < 0.1 { 18 } else { 80 };
    for phase in 0..s.ceil().max(1.0) as u32 {
        let point = |d| {
            if horizontal {
                (x, y + phase + d)
            } else {
                (x + phase + d, y)
            }
        };
        let (ex, ey) = point(outer);
        if ex >= frame.width || ey >= frame.height {
            continue;
        }
        let (ax, ay) = point(0);
        let a = rgb(frame, ax, ay);
        let c = rgb(frame, ex, ey);
        if !(0..3).all(|i| a[i] < 180 && c[i] < 180 && a[i].abs_diff(c[i]) <= tolerance) {
            continue;
        }
        for middle in [s.floor().max(1.0) as u32, s.ceil().max(1.0) as u32] {
            let (bx, by) = point(middle);
            let b = rgb(frame, bx, by);
            if (0..3).any(|i| {
                let d = i16::from(b[i]) - i16::from(a[i]);
                let e = i16::from(b[i]) - i16::from(c[i]);
                (d >= 18 && e >= 18) || (d <= -18 && e <= -18)
            }) {
                return true;
            }
        }
    }
    false
}
fn panel(frame: &Frame, dot: Dot, s: f32) -> Option<Panel> {
    let from = dot.y1 + (6.0 * s).round() as u32;
    let end = (dot.y1 + (100.0 * s).round() as u32).min(frame.height);
    let ys = (from..end).step_by((6.0 * s).round().max(3.0) as usize);
    let n = ys.clone().count();
    if n < 8 {
        return None;
    }
    let score = |x| ys.clone().filter(|&y| edge(frame, x, y, s, false)).count() * 100 / n;
    let lo = dot.x0.saturating_sub((28.0 * s).ceil() as u32);
    let hi = dot.x0.saturating_sub((4.0 * s).floor() as u32);
    let left = (lo..hi).max_by_key(|&x| score(x))?;
    if score(left) < 65 {
        return None;
    }
    let right = (left + (140.0 * s).round() as u32
        ..(left + (740.0 * s).round() as u32).min(frame.width.saturating_sub(2)))
        .find(|&x| score(x) >= 65)?;
    let xs = (left + 5..right.saturating_sub(4)).step_by((6.0 * s).round().max(3.0) as usize);
    let total = xs.clone().count();
    let cap = (dot.y0.saturating_sub((26.0 * s).ceil() as u32)
        ..dot.y0.saturating_sub((5.0 * s).floor() as u32))
        .find(|&y| {
            total >= 10
                && xs.clone().filter(|&x| edge(frame, x, y, s, true)).count() * 10 >= total * 7
        });
    let top = cap.unwrap_or_else(|| dot.y0.saturating_sub((15.0 * s).round() as u32));
    let (mut last, mut gap) = (dot.y1, 0);
    for y in dot.y1..(dot.y1 + (700.0 * s).ceil() as u32).min(frame.height) {
        if edge(frame, left, y, s, false) || edge(frame, right, y, s, false) {
            last = y;
            gap = 0
        } else {
            gap += 1
        }
        if gap > (10.0 * s).ceil() as u32 {
            break;
        }
    }
    let bottom = (last + 1).min(frame.height);
    if bottom < top + (80.0 * s).round() as u32 {
        return None;
    }
    let rect = BoxRect {
        x: left,
        y: top,
        w: (right + (3.0 * s).ceil() as u32).min(frame.width) - left,
        h: bottom - top,
    };
    let mut dark = 0;
    let mut all = 0;
    for y in (top + 6..bottom.saturating_sub(5)).step_by(13) {
        for x in (left + 6..right.saturating_sub(5)).step_by(13) {
            all += 1;
            dark += usize::from(rgb(frame, x, y).iter().all(|v| *v < 185));
        }
    }
    let bright = count(
        frame,
        dot.x1 + 2,
        dot.y0.saturating_sub(4),
        right.saturating_sub(dot.x1 + 6),
        (dot.y1 - dot.y0) + 8,
        |p| title_light(p).is_some_and(|v| v >= 150),
    );
    if all == 0 || dark * 10 < all * 6 || bright < 16 {
        return None;
    }
    Some(Panel {
        rect,
        cap: cap.is_some(),
    })
}

fn title_marker(frame: &Frame, dot: Dot) -> bool {
    if dot.x0 < 5 || dot.y0 == 0 {
        return false;
    }
    let mid = (dot.y0 + dot.y1) / 2;
    (dot.x0 - 5..dot.x0 - 2).all(|x| {
        (mid - 1..=mid + 1).all(|y| {
            if y >= frame.height {
                return false;
            }
            let p = rgb(frame, x, y);
            u32::from(p[0]) * 30 + u32::from(p[1]) * 59 + u32::from(p[2]) * 11 < 13000
                && p[2] >= p[0]
        })
    })
}

fn panel_still_present(frame: &Frame, panel: Panel, s: f32) -> bool {
    let r = panel.rect;
    if r.right() > frame.width || r.bottom() > frame.height {
        return false;
    }
    let right = r.right().saturating_sub((3.0 * s).ceil() as u32);
    let ys = (r.y + (24.0 * s).round() as u32..r.bottom().saturating_sub(6))
        .step_by((10.0 * s).round().max(6.0) as usize);
    let total = ys.clone().count();
    if total < 5 || ys.clone().filter(|&y| edge(frame, r.x, y, s, false)).count() * 10 < total * 6
        || ys.filter(|&y| edge(frame, right, y, s, false)).count() * 10 < total * 6 {
        return false;
    }
    let (mut dark, mut total) = (0, 0);
    for y in (r.y + 24..r.bottom().saturating_sub(6)).step_by(17) {
        for x in (r.x + 6..right.saturating_sub(5)).step_by(17) {
            total += 1;
            dark += usize::from(rgb(frame, x, y).iter().all(|v| *v < 185));
        }
    }
    total > 0 && dark * 10 >= total * 6
}

impl Selector {
    pub fn select(
        &mut self,
        capture: &ItemCapture,
        markers: &[Dot],
        scale_hint: Option<f32>,
    ) -> Association {
        let (px, py) = (
            capture.pointer.x - capture.origin.x,
            capture.pointer.y - capture.origin.y,
        );
        let frame = &capture.frame;
        let scope = (capture.origin.x, capture.origin.y, frame.width, frame.height);
        let found = source(frame, px, py, self.inventory.as_ref(), scale_hint);
        self.inventory = found.clone();
        let Some(inv) = found else {
            // A temporarily covered header must not make the second identical
            // frame fall back to the comparison nearest the pointer. Retain one
            // bounded source until proof returns or this pointer/capture leaves
            // its scope; no stale source can choose an item.
            let rejected = self.bound_source.is_some_and(|(rect, previous)| {
                previous == scope && rect.contains(px, py)
            });
            if !rejected {
                self.bound_source = None;
                self.pair = None;
            }
            return Association {
                panel: None,
                rejected,
                metadata: json!({"state":if rejected {"rejected"} else {"normal"},"token":null,"guards":[]}),
            };
        };
        let s = inv.scale;
        if self.pair.is_some_and(|pair| pair.scope != scope || pair.source != inv.rect) {
            self.pair = None;
        }
        let gx = inv.rect.x + (7.0 * s).round() as u32;
        let gy = inv.rect.y + (47.0 * s).round() as u32;
        let pitch = 36.0 * s;
        let (dx, dy) = (px - gx as i32, py - gy as i32);
        let valid = dx >= 0
            && dy >= 0
            && (dx as f32) < pitch * 5.0
            && (dy as f32) < pitch * 6.0
            && (dx as f32) % pitch < 32.0 * s
            && (dy as f32) % pitch < 32.0 * s;
        let slot = if valid {
            Some(BoxRect {
                x: gx + ((dx as f32 / pitch).floor() * pitch).round() as u32,
                y: gy + ((dy as f32 / pitch).floor() * pitch).round() as u32,
                w: (32.0 * s).round() as u32,
                h: (32.0 * s).round() as u32,
            })
        } else {
            None
        };
        let context = format!(
            "{}:{}:{}:{}:{}:{}:{}:{}:{}",
            capture.origin.x,
            capture.origin.y,
            frame.width,
            frame.height,
            inv.rect.x,
            inv.rect.y,
            inv.tab,
            slot.map(|r| r.x).unwrap_or(0),
            slot.map(|r| r.y).unwrap_or(0)
        );
        let header = BoxRect {
            h: (45.0 * s).round() as u32,
            ..inv.rect
        };
        let mut metadata = json!({"state":"normal","token":context,"source":inv.rect.global(capture),"slot":slot.map(|r|r.global(capture)),"guards":[header.global(capture)]});
        self.bound_source = Some((inv.rect, scope));
        if !valid {
            metadata["state"] = json!("rejected");
            return Association {
                panel: None,
                rejected: true,
                metadata,
            };
        }
        let candidates: Vec<_> = markers
            .iter()
            .filter(|d| {
                (d.x0 as i32 - px).abs() as f32 <= 640.0 * s
                    && (d.y0 as i32 - py).abs() as f32 <= 640.0 * s
            })
            .filter(|&&d| title_marker(frame, d))
            .take(25)
            .copied()
            .collect();
        if candidates.len() > 24 {
            metadata["state"] = json!("rejected");
            return Association {
                panel: None,
                rejected: true,
                metadata,
            };
        }
        let mut panels: Vec<Panel> = candidates
            .into_iter()
            .filter_map(|d| panel(frame, d, s))
            .collect();
        panels.sort_by_key(|p| p.rect.x);
        panels.dedup_by(|a, b| a.rect.x.abs_diff(b.rect.x) < 4 && a.rect.y.abs_diff(b.rect.y) < 4);
        if panels.len() < 2 {
            // A known pair can briefly lose one cyan marker while both native
            // frames remain. That is not proof of an ordinary single popup:
            // nearest-marker fallback could then price the equipped comparison.
            if self.pair.is_some_and(|pair| pair.panels.into_iter()
                .all(|panel| panel_still_present(frame, panel, pair.scale))) {
                metadata["state"] = json!("rejected");
                return Association { panel: None, rejected: true, metadata };
            }
            // A genuinely departed pair leaves the ordinary single path intact.
            self.bound_source = None;
            self.pair = None;
            return Association {
                panel: None,
                rejected: false,
                metadata,
            };
        }
        let mut chosen = None;
        if panels.len() == 2 {
            let (a, b) = (panels[0], panels[1]);
            let paired = a.rect.right() <= b.rect.x
                && b.rect.x - a.rect.right() <= (8.0 * s).ceil() as u32
                && a.rect.y.abs_diff(b.rect.y) <= (4.0 * s).ceil() as u32
                && (a.cap || b.cap)
                && a.rect.w as f32 / b.rect.w as f32 >= 0.7
                && a.rect.w as f32 / b.rect.w as f32 <= 1.4;
            let fitted = b.rect.right().abs_diff(inv.rect.right()) <= (8.0 * s).ceil() as u32
                && frame.width.saturating_sub(b.rect.right()) <= (24.0 * s).ceil() as u32
                && a.rect.x + ((30.0 * s).round() as u32) < inv.rect.x;
            if paired && fitted && !panels.iter().any(|p| p.rect.contains(px, py)) {
                chosen = Some(a.rect);
                self.pair = Some(PairBinding { source: inv.rect, scope, panels: [a, b], scale: s });
            }
        }
        let rejected = chosen.is_none();
        metadata["state"] = json!(if rejected {
            "rejected"
        } else {
            "inventory-primary"
        });
        if let Some(rect) = chosen {
            metadata["panel"] = rect.global(capture);
            let h = (12.0 * s).round().max(4.0) as u32;
            let w = s.round().max(1.0) as u32;
            let y = rect.y + (42.0 * s).round() as u32;
            for x in [rect.x, rect.right().saturating_sub((3.0 * s).ceil() as u32)] {
                metadata["guards"]
                    .as_array_mut()
                    .unwrap()
                    .push(BoxRect { x, y, w, h }.global(capture));
            }
        }
        Association {
            panel: chosen,
            rejected,
            metadata,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use minerva_core::ScreenPoint;

    fn paint(f: &mut Frame, x: u32, y: u32, w: u32, h: u32, p: [u8; 3]) {
        for yy in y..y + h {
            for xx in x..x + w {
                let at = ((yy * f.width + xx) * 4) as usize;
                f.rgba[at..at + 3].copy_from_slice(&p)
            }
        }
    }
    fn fixture(tab: u32, gap: u32) -> (ItemCapture, Vec<Dot>, BoxRect) {
        let mut f = Frame {
            width: 1500,
            height: 900,
            rgba: [20, 35, 20, 255].repeat(1500 * 900),
            at_ms: 1000,
        };
        let inv = BoxRect {
            x: 1293,
            y: 90,
            w: 207,
            h: 285,
        };
        paint(&mut f, inv.x, inv.y, inv.w, inv.h, [245, 246, 247]);
        paint(&mut f, inv.x + 4, inv.y + 2, 199, 17, [255, 255, 255]);
        for x in (inv.x + 8..inv.x + 128).step_by(6) {
            paint(&mut f, x, inv.y + 7, 2, 6, [0, 0, 0]);
        }
        for (cx, colour) in [
            (168, [220, 85, 68]),
            (181, [220, 85, 68]),
            (194, [51, 153, 204]),
        ] {
            paint(&mut f, inv.x + cx - 4, inv.y + 5, 8, 10, colour);
        }
        for i in 0..6 {
            paint(
                &mut f,
                inv.x + 6 + 33 * i,
                inv.y + 23,
                29,
                17,
                if i == tab {
                    [234, 101, 129]
                } else {
                    [180, 180, 180]
                },
            );
        }
        let b = BoxRect {
            x: 1263,
            y: 180,
            w: 236,
            h: 240,
        };
        let a = BoxRect {
            x: b.x - gap - 236,
            y: 180,
            w: 236,
            h: 270,
        };
        let mut dots = Vec::new();
        for r in [a, b] {
            paint(&mut f, r.x, r.y, r.w, r.h, [30, 30, 70]);
            paint(&mut f, r.x + 1, r.y, 1, r.h, [190, 190, 205]);
            paint(&mut f, r.right() - 2, r.y, 1, r.h, [190, 190, 205]);
            paint(&mut f, r.x, r.y + 1, r.w, 1, [190, 190, 205]);
            let d = Dot {
                x0: r.x + 9,
                y0: r.y + 15,
                x1: r.x + 14,
                y1: r.y + 20,
            };
            for y in d.y0..d.y1 {
                for x in d.x0..d.x1 {
                    if (x as i32 - (d.x0 + 2) as i32).abs() + (y as i32 - (d.y0 + 2) as i32).abs()
                        <= 2
                    {
                        paint(&mut f, x, y, 1, 1, [85, 204, 255]);
                    }
                }
            }
            for x in (d.x1 + 3..d.x1 + 75).step_by(5) {
                paint(&mut f, x, r.y + 12, 2, 12, [240, 240, 240]);
            }
            dots.push(d);
        }
        (
            ItemCapture {
                frame: f,
                origin: ScreenPoint { x: 1700, y: -200 },
                pointer: ScreenPoint {
                    x: 1700 + 1378,
                    y: -200 + 152,
                },
            },
            dots,
            a,
        )
    }

    #[test]
    fn source_slot_and_fitted_pair_choose_primary_before_ocr() {
        for tab in [0, 4] {
            let (capture, dots, expected) = fixture(tab, 3);
            let mut selector = Selector::default();
            let result = selector.select(&capture, &dots, None);
            assert!(!result.rejected);
            assert_eq!(result.panel, Some(expected));
            assert_eq!(result.metadata["state"], "inventory-primary");
            assert_eq!(result.metadata["panel"]["x"], expected.x + 1700);
            assert_eq!(result.metadata["source"]["y"], -110);
            assert_eq!(result.metadata["slot"]["width"], 32);
            assert_eq!(result.metadata["guards"].as_array().unwrap().len(), 3);
            assert_eq!(
                selector.select(&capture, &dots, None).metadata["token"],
                result.metadata["token"]
            );
        }
    }

    #[test]
    fn unsafe_cell_gutter_and_ambiguous_pairs_are_rejected() {
        let (mut capture, dots, _) = fixture(0, 3);
        capture.pointer.y = capture.origin.y + 225; // Real native comparison covers this cell.
        let result = Selector::default().select(&capture, &dots, None);
        assert!(result.rejected);
        assert!(result.panel.is_none());
        capture.pointer.y = capture.origin.y + 152;
        capture.pointer.x = capture.origin.x + 1293 + 7 + 33; // Four-pixel grid gutter.
        assert!(Selector::default().select(&capture, &dots, None).rejected);
        let (capture, dots, _) = fixture(0, 18);
        assert!(Selector::default().select(&capture, &dots, None).rejected);
    }

    #[test]
    fn nearby_inventory_does_not_override_linked_or_single_equipped_titles() {
        let (mut capture, dots, _) = fixture(0, 3);
        capture.pointer.x = capture.origin.x + 700;
        let result = Selector::default().select(&capture, &dots, None);
        assert!(!result.rejected);
        assert!(result.panel.is_none());
        capture.pointer.x = capture.origin.x + 1378;
        let result = Selector::default().select(&capture, &dots[..1], None);
        assert!(!result.rejected);
        assert!(result.panel.is_none());
        paint(&mut capture.frame, 1293, 90, 207, 45, [245, 246, 247]);
        let result = Selector::default().select(&capture, &dots, None);
        assert!(!result.rejected);
        assert!(result.panel.is_none());
    }

    #[test]
    fn lost_source_and_slot_changes_invalidate_context() {
        let (mut capture, dots, _) = fixture(0, 3);
        let mut selector = Selector::default();
        let first = selector.select(&capture, &dots, None);
        assert!(first.panel.is_some());
        capture.pointer.x += 36;
        let second = selector.select(&capture, &dots, None);
        assert!(second.panel.is_some());
        assert_ne!(first.metadata["token"], second.metadata["token"]);
        paint(&mut capture.frame, 1293, 90, 207, 45, [245, 246, 247]);
        let rejected = selector.select(&capture, &dots, None);
        assert!(rejected.rejected);
        assert!(rejected.metadata["token"].is_null());
        for _ in 0..3 {
            assert!(selector.select(&capture, &dots, None).rejected);
        }
        let (recovered, fresh_dots, _) = fixture(0, 3);
        assert!(selector.select(&recovered, &fresh_dots, None).panel.is_some());
        capture.pointer.x = capture.origin.x + 700;
        assert!(!selector.select(&capture, &dots, None).rejected);
    }

    #[test]
    fn a_lost_source_denial_does_not_leak_to_another_capture_origin() {
        let (mut capture, dots, _) = fixture(0, 3);
        let mut selector = Selector::default();
        assert!(selector.select(&capture, &dots, None).panel.is_some());
        paint(&mut capture.frame, 1293, 90, 207, 45, [245, 246, 247]);
        assert!(selector.select(&capture, &dots, None).rejected);
        capture.origin.x += 100;
        capture.pointer.x += 100;
        assert!(!selector.select(&capture, &dots, None).rejected);
    }

    #[test]
    fn missing_primary_marker_in_a_known_pair_never_falls_back_to_comparison() {
        let (mut capture, dots, expected) = fixture(0, 3);
        let mut selector = Selector::default();
        assert_eq!(selector.select(&capture, &dots, None).panel, Some(expected));
        let primary = dots[0];
        paint(&mut capture.frame, primary.x0, primary.y0,
            primary.x1 - primary.x0, primary.y1 - primary.y0, [30, 30, 70]);
        for _ in 0..3 {
            let held = selector.select(&capture, &dots[1..], None);
            assert!(held.rejected);
            assert_eq!(held.metadata["state"], "rejected");
            assert!(held.panel.is_none());
        }
        // Losing the upper cap as well does not make the still-framed dark
        // primary body an ordinary single comparison description.
        paint(&mut capture.frame, expected.x, expected.y, expected.w, 3, [20, 35, 20]);
        assert!(selector.select(&capture, &dots[1..], None).rejected);
        let (mut restored, fresh_dots, _) = fixture(0, 3);
        restored.pointer.x += 36;
        assert_eq!(selector.select(&restored, &fresh_dots, None).panel, Some(expected));
    }

    #[test]
    fn actual_pair_departure_releases_the_ordinary_single_description_path() {
        for removed in [0, 1] {
            let (mut capture, dots, primary) = fixture(0, 3);
            let mut selector = Selector::default();
            assert!(selector.select(&capture, &dots, None).panel.is_some());
            let gone = if removed == 0 { primary } else { BoxRect { x: 1263, y: 180, w: 236, h: 240 } };
            paint(&mut capture.frame, gone.x, gone.y, gone.w, gone.h, [20, 35, 20]);
            let remaining = if removed == 0 { &dots[1..] } else { &dots[..1] };
            let single = selector.select(&capture, remaining, None);
            assert!(!single.rejected);
            assert!(single.panel.is_none());
            assert_eq!(single.metadata["state"], "normal");
        }
    }

    #[test]
    fn pointers_outside_the_captured_image_do_not_enter_source_search() {
        let (mut capture, dots, _) = fixture(0, 3);
        for (x, y) in [(3000, 200), (200, 2000), (-1, 150)] {
            capture.pointer.x = capture.origin.x + x;
            capture.pointer.y = capture.origin.y + y;
            let result = Selector::default().select(&capture, &dots, None);
            assert!(!result.rejected);
            assert!(result.panel.is_none());
        }
    }

    #[test]
    fn a_pair_without_caps_is_not_bound_and_coloured_titles_keep_their_role() {
        let (mut capture, dots, expected) = fixture(0, 3);
        for d in &dots {
            paint(
                &mut capture.frame,
                d.x1 + 3,
                d.y0 - 3,
                72,
                12,
                [255, 153, 0],
            );
        }
        assert_eq!(
            Selector::default().select(&capture, &dots, None).panel,
            Some(expected)
        );
        for x in [expected.x, 1263] {
            paint(&mut capture.frame, x, 180, 236, 3, [30, 30, 70]);
        }
        let result = Selector::default().select(&capture, &dots, None);
        assert!(result.rejected);
        assert!(result.panel.is_none());
    }

    #[test]
    fn association_uses_frame_pixels_with_fractional_dpi_and_nonzero_origin() {
        let (capture, _, _) = fixture(0, 3);
        let original = image::RgbaImage::from_raw(
            capture.frame.width,
            capture.frame.height,
            capture.frame.rgba.clone(),
        )
        .unwrap();
        for scale in [1.25_f32, 1.5, 2.0] {
            let resized = image::imageops::resize(
                &original,
                (original.width() as f32 * scale).round() as u32,
                (original.height() as f32 * scale).round() as u32,
                image::imageops::FilterType::Triangle,
            );
            let scaled = ItemCapture {
                frame: Frame {
                    width: resized.width(),
                    height: resized.height(),
                    rgba: resized.into_raw(),
                    at_ms: 2000,
                },
                origin: capture.origin,
                pointer: ScreenPoint {
                    x: capture.origin.x
                        + ((capture.pointer.x - capture.origin.x) as f32 * scale).round() as i32,
                    y: capture.origin.y
                        + ((capture.pointer.y - capture.origin.y) as f32 * scale).round() as i32,
                },
            };
            let (_, dots) = crate::tooltip_surface::prepare(&scaled.frame);
            let result = Selector::default().select(&scaled, &dots, Some(scale));
            if result.panel.is_none() {
                eprintln!(
                    "scale={scale}, candidates={:?}",
                    dots.iter()
                        .map(|d| (
                            (d.x0, d.y0, d.x1, d.y1),
                            title_marker(&scaled.frame, *d),
                            panel(&scaled.frame, *d, scale).map(|p| p.rect)
                        ))
                        .collect::<Vec<_>>()
                );
            }
            assert!(result.panel.is_some(), "scale {scale}: {}", result.metadata);
            let slot = &result.metadata["slot"];
            assert!(
                (slot["x"].as_i64().unwrap() - (1700 + (1372.0 * scale).round() as i64)).abs() <= 2,
                "{scale}: {slot}"
            );
        }
    }
}
