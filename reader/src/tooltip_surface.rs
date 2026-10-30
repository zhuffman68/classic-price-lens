//! Contrast adaptation inside structurally verified native tooltip frames.
//! The captured source stays untouched; the pinned reader validates the title.
use minerva_core::Frame;

#[derive(Clone, Copy)]
pub(crate) struct Dot {
    pub x0: u32,
    pub y0: u32,
    pub x1: u32,
    pub y1: u32,
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
    use super::*;

    #[test]
    fn orange_and_coloured_title_ink_retains_antialiased_strokes() {
        for p in [[255,153,0],[170,105,45],[255,230,80],[190,100,240]] {
            assert!(super::title_light(p).is_some_and(|v|v>=145));
        }
        assert!(super::title_light([70,40,110]).is_none_or(|v|v<130));
    }

    fn title_frame(ink: [u8; 3]) -> Frame {
        let mut frame = Frame {width: 80, height: 20, rgba: [30,30,70,255].repeat(1600), at_ms: 0};
        for y in 7..12 {
            for x in 8..13 {
                if (x as i32 - 10).abs() + (y as i32 - 9).abs() <= 2 {
                    let at = ((y * frame.width + x) * 4) as usize;
                    frame.rgba[at..at+3].copy_from_slice(&ink);
                }
            }
        }
        frame
    }

    #[test]
    fn retry_crop_excludes_only_the_leading_round_cyan_marker() {
        let frame = title_frame([85,204,255]);
        assert_eq!(name_glyph_start(&frame, 8, 4, 60, 12, true), 15);
        // The public bounds remain untouched and a later cyan component is not
        // a title marker. This also covers the marker-free centered-title path.
        assert_eq!(name_glyph_start(&frame, 3, 4, 65, 12, true), 3);
    }

    #[test]
    fn retry_crop_preserves_orange_names_and_real_punctuation() {
        for colour in [[255,153,0], [255,255,255], [190,100,240]] {
            let frame = title_frame(colour);
            assert_eq!(name_glyph_start(&frame, 8, 4, 60, 12, true), 8);
        }
        let mut frame = title_frame([85,204,255]);
        // A tall cyan glyph clipped by the text bounds is not the small marker.
        for y in 4..16 {
            let at = ((y * frame.width + 8) * 4) as usize;
            frame.rgba[at..at+3].copy_from_slice(&[85,204,255]);
        }
        assert_eq!(name_glyph_start(&frame, 8, 4, 60, 12, true), 8);
    }

    #[test]
    fn centered_cyan_leading_glyph_is_never_cropped_as_a_bullet() {
        let frame=title_frame([85,204,255]);
        // The same compact cyan component can be a real first glyph or
        // punctuation in a marker-free centered title. Colour/shape alone do
        // not authorize removing it; retain the originating reader's proof.
        assert_eq!(name_glyph_start(&frame,8,4,60,12,false),8);
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

pub(crate) fn dots_in(width: u32, height: u32, pixel: impl Fn(u32, u32) -> [u8; 3]) -> Vec<Dot> {
    let count = (width * height) as usize;
    let mut mask: Vec<u8> = (0..count)
        .map(|i| u8::from(cyan(pixel(i as u32 % width, i as u32 / width))))
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
                (y + 1 < height).then_some(at + width),
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

fn dots(frame: &Frame) -> Vec<Dot> {
    dots_in(frame.width, frame.height, |x, y| rgb(frame, x, y))
}

/// Minerva's verified name bounds include the cyan bullet, whereas its primary
/// glyph crop does not. A retry must not turn that decoration into punctuation.
/// Centered/marker-free names keep their complete crop, including punctuation.
pub(crate) fn name_glyph_start(frame: &Frame, x: u32, y: u32, w: u32, h: u32, marker_title: bool) -> u32 {
    if !marker_title { return x }
    let width = w.min(12);
    let markers = dots_in(width, h, |col, row| rgb(frame, x + col, y + row));
    let mut leading = markers.into_iter().filter(|dot| {
        dot.x0 == 0 && dot.x1 < w && dot.y0 > 0 && dot.y1 < h
    });
    match (leading.next(), leading.next()) {
        (Some(dot), None) => x + (dot.x1 + 2).min(w),
        _ => x,
    }
}

pub fn prepare(frame: &Frame) -> (Option<Frame>, Vec<Dot>) {
    let mut prepared = None;
    let markers=dots(frame);
    for &dot in &markers {
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
    (prepared,markers)
}
