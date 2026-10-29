//! Contrast adaptation inside structurally verified native tooltip frames.
//! The captured source stays untouched; the pinned reader validates the title.
use minerva_core::Frame;

#[derive(Clone, Copy)]
struct Dot {
    x0: u32,
    y0: u32,
    x1: u32,
    y1: u32,
}

pub(crate) fn rgb(frame: &Frame, x: u32, y: u32) -> [u8; 3] {
    let at = ((y * frame.width + x) * 4) as usize;
    [frame.rgba[at], frame.rgba[at + 1], frame.rgba[at + 2]]
}
fn luma(p: [u8; 3]) -> f32 {
    p[0] as f32 * 0.30 + p[1] as f32 * 0.59 + p[2] as f32 * 0.11
}
fn fill(p: [u8; 3]) -> bool {
    luma(p) < 130.0 && p[2] >= p[0]
}
fn cyan(p: [u8; 3]) -> bool {
    p[2] >= 200 && p[1] >= 140 && p[0] <= 140 && p[1].saturating_sub(p[0]) >= 70
}
fn coloured(p: [u8; 3]) -> bool {
    let high = *p.iter().max().unwrap();
    let low = *p.iter().min().unwrap();
    high >= 145 && high - low > 45
}

/// Title pixels can be orange, yellow or purple after scrolling. Shared by the
/// marker-based and centered-header readers, only inside verified native panels.
pub(crate) fn title_light(p: [u8; 3]) -> Option<u8> {
    let [r,g,b]=p;
    let neutral=r.abs_diff(g)<=55 && b.saturating_sub(r)<100;
    if neutral {Some((u16::from(r)*30/100+u16::from(g)*59/100+u16::from(b)*11/100) as u8)}
    else if coloured(p) {Some(*p.iter().max().unwrap())}
    else {None}
}

#[cfg(test)]
mod title_tests {
    #[test]
    fn orange_and_coloured_title_ink_retains_antialiased_strokes() {
        for p in [[255,153,0],[170,105,45],[255,230,80],[190,100,240]] {
            assert!(super::title_light(p).is_some_and(|v|v>=145));
        }
        assert!(super::title_light([70,40,110]).is_none_or(|v|v<130));
    }
}

fn title_ink(frame: &Frame, dot: Dot, x: u32, y: u32) -> bool {
    // The cyan marker's antialiased fringe is not part of the item title.
    !(x < dot.x1 + 2 && y >= dot.y0.saturating_sub(2) && y < dot.y1 + 2)
        && coloured(rgb(frame, x, y))
}

// Classic's rim has dark strokes around a one-pixel translucent gap. Unlike
// fill hue, that repeated geometry survives warm chat showing through it.
pub(crate) fn rim(frame: &Frame, x: u32, y: u32) -> bool {
    let (a, b, c) = (rgb(frame, x, y), rgb(frame, x + 1, y), rgb(frame, x + 2, y));
    stroke_gap(a, b, c)
}

pub(crate) fn horizontal_rim(frame: &Frame, x: u32, y: u32) -> bool {
    stroke_gap(rgb(frame, x, y), rgb(frame, x, y + 1), rgb(frame, x, y + 2))
}

fn stroke_gap(a: [u8; 3], b: [u8; 3], c: [u8; 3]) -> bool {
    *a.iter().max().unwrap() < 180
        && *c.iter().max().unwrap() < 180
        && (0..3).all(|i| a[i].abs_diff(c[i]) < 65)
        && luma(b) > luma(a).max(luma(c)) * 1.45 + 15.0
}
fn rim_score(frame: &Frame, x: u32, top: u32, bottom: u32) -> f32 {
    let ys = (top..bottom).step_by(6);
    let total = ys.clone().count();
    if total < 5 {
        return 0.0;
    }
    ys.filter(|&y| rim(frame, x, y)).count() as f32 / total as f32
}

fn dots(frame: &Frame) -> Vec<Dot> {
    let width = frame.width;
    let count = (width * frame.height) as usize;
    let mut mask: Vec<u8> = frame
        .rgba
        .chunks_exact(4)
        .map(|p| u8::from(cyan([p[0], p[1], p[2]])))
        .collect();
    let mut result = Vec::new();
    let mut queue = Vec::new();
    for start in 0..count {
        if mask[start] == 0 {
            continue;
        }
        mask[start] = 0;
        queue.push(start as u32);
        let (sx, sy) = (start as u32 % width, start as u32 / width);
        let mut dot = Dot {
            x0: sx,
            y0: sy,
            x1: sx + 1,
            y1: sy + 1,
        };
        let mut pixels = 0;
        while let Some(at) = queue.pop() {
            let (x, y) = (at % width, at / width);
            pixels += 1;
            dot.x0 = dot.x0.min(x);
            dot.x1 = dot.x1.max(x + 1);
            dot.y0 = dot.y0.min(y);
            dot.y1 = dot.y1.max(y + 1);
            for next in [
                x.checked_sub(1).map(|v| y * width + v),
                (x + 1 < width).then_some(at + 1),
                y.checked_sub(1).map(|v| v * width + x),
                (y + 1 < frame.height).then_some(at + width),
            ]
            .into_iter()
            .flatten()
            {
                if mask[next as usize] != 0 {
                    mask[next as usize] = 0;
                    queue.push(next)
                }
            }
        }
        let (w, h) = (dot.x1 - dot.x0, dot.y1 - dot.y0);
        if (4..=11).contains(&w)
            && (4..=11).contains(&h)
            && w.abs_diff(h) <= 3
            && pixels * 2 >= w * h
        {
            result.push(dot)
        }
    }
    result
}

pub fn prepare(frame: &Frame) -> Option<Frame> {
    let mut prepared = None;
    for dot in dots(frame) {
        if dot.x0 < 5 || dot.y0 < 2 {
            continue;
        }
        let top = dot.y0.saturating_sub(4);
        let bottom = (dot.y0 + 120).min(frame.height);
        let left = (dot.x0.saturating_sub(28)..dot.x0 - 3)
            .map(|x| (rim_score(frame, x, top, bottom), x))
            .max_by(|a, b| a.0.total_cmp(&b.0).then(a.1.cmp(&b.1)));
        let Some((_, left)) = left.filter(|p| p.0 >= 0.55) else {
            continue;
        };
        let Some(right) = (left + 70..(left + 740).min(frame.width.saturating_sub(2)))
            .find(|&x| rim_score(frame, x, top, bottom) >= 0.55)
        else {
            continue;
        };
        let height = dot.y1 - dot.y0;
        let y0 = dot.y0.saturating_sub(2 * height);
        let y1 = (dot.y1 + 2 * height).min(frame.height);
        let mid = (dot.y0 + dot.y1) / 2;
        let repair = (dot.x0 - 5..dot.x0 - 2).any(|x| {
            (mid - 1..=mid + 1).any(|y| {
                let p = rgb(frame, x, y);
                !fill(p) && *p.iter().max().unwrap() < 180
            })
        });
        let colour = (y0..y1).any(|y| (dot.x1..right).any(|x| title_ink(frame, dot, x, y)));
        if !repair && !colour {
            continue;
        }
        let target = prepared.get_or_insert_with(|| frame.clone());
        for x in dot.x0 - 5..dot.x0 - 2 {
            for y in mid - 1..=mid + 1 {
                if *rgb(frame, x, y).iter().max().unwrap() < 180 {
                    let at = ((y * frame.width + x) * 4) as usize;
                    target.rgba[at..at + 3].copy_from_slice(&[50, 45, 80]);
                }
            }
        }
        for y in y0..y1 {
            for x in dot.x1..right {
                let p = rgb(frame, x, y);
                if title_ink(frame, dot, x, y) {
                    let shade = *p.iter().max().unwrap();
                    let at = ((y * frame.width + x) * 4) as usize;
                    target.rgba[at..at + 3].fill(shade)
                }
            }
        }
    }
    prepared
}
