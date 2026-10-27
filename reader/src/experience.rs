//! Local pixel readers only. All readers share Minerva's bundled recognition model.
use minerva_core::{
    ExpBar, ExpBarReader, ExpFigures, Frame, ScreenPoint, ScreenRect, StatusBarCapture,
    StatusBarReader, TitleCapture, TitleReader,
};
use serde_json::{Value, json};

pub struct ExperienceReader {
    status: StatusBarReader,
    exp: ExpBarReader,
    title: TitleReader,
    previous: Option<(u32, u32, i32, i32, Vec<u8>, Value)>,
    exp_previous: Option<(ScreenRect, Vec<u8>, Option<ExpBar>)>,
}

impl ExperienceReader {
    pub fn new() -> Self {
        Self {
            status: StatusBarReader::bundled(),
            exp: ExpBarReader::bundled(),
            title: TitleReader::bundled(),
            previous: None,
            exp_previous: None,
        }
    }

    pub fn read(&mut self, frame: Frame, origin: ScreenPoint, read_map: bool) -> Value {
        // The status bar is pinned to the bottom; a small strip also covers 2x UI.
        let height = frame.height.min(256);
        let y = frame.height - height;
        let offset = y as usize * frame.width as usize * 4;
        let strip_origin = ScreenPoint {
            x: origin.x,
            y: origin.y + y as i32,
        };
        let pixels = &frame.rgba[offset..];
        let cached = self.previous.as_ref().is_some_and(|(w, h, x, y, old, _)| {
            *w == frame.width
                && *h == height
                && *x == strip_origin.x
                && *y == strip_origin.y
                && old == pixels
        });
        let mut value = if cached {
            self.previous.as_ref().unwrap().5.clone()
        } else {
            let capture = StatusBarCapture {
                frame: Frame {
                    width: frame.width,
                    height,
                    rgba: pixels.to_vec(),
                    at_ms: frame.at_ms,
                },
                origin: strip_origin,
            };
            let status = self.status.read(&capture);
            let area = status.bar.as_ref().and_then(|b| b.exp_figures);
            let patch = area.and_then(|r| figure_pixels(&capture, r));
            let exp_cached = self
                .exp_previous
                .as_ref()
                .is_some_and(|(r, p, _)| Some(*r) == area && Some(p) == patch.as_ref());
            let bar = if exp_cached {
                self.exp_previous.as_ref().unwrap().2
            } else {
                self.exp
                    .read_status_bar(
                        &capture,
                        status.bar.as_ref(),
                        ExpFigures { last_found: None },
                    )
                    .bar
            };
            self.exp_previous = area.zip(patch).map(|(r, p)| (r, p, bar));
            let result = json!({"bar":bar,"expCached":exp_cached,
                "level":status.bar.as_ref().and_then(|b|b.level),
                "character":status.bar.as_ref().and_then(|b|b.name.clone()),
                "job":status.bar.as_ref().and_then(|b|b.job.clone()),
                "area":area});
            self.previous = Some((
                frame.width,
                height,
                strip_origin.x,
                strip_origin.y,
                pixels.to_vec(),
                result.clone(),
            ));
            result
        };
        value["cached"] = json!(cached);
        if cached {
            value["expCached"] = json!(true);
        }
        value["mapRead"] = json!(read_map);
        if read_map {
            value["map"] = serde_json::to_value(
                self.title
                    .read(&TitleCapture {
                        frame,
                        origin,
                        ours: vec![],
                    })
                    .lines,
            )
            .unwrap_or(Value::Null);
        }
        value
    }
}

fn figure_pixels(capture: &StatusBarCapture, area: ScreenRect) -> Option<Vec<u8>> {
    let left = u32::try_from(area.x - capture.origin.x).ok()?;
    let top = u32::try_from(area.y - capture.origin.y).ok()?;
    let frame = &capture.frame;
    if left.checked_add(area.width)? > frame.width || top.checked_add(area.height)? > frame.height {
        return None;
    }
    let mut pixels = Vec::with_capacity(area.width as usize * area.height as usize * 4);
    for y in top..top + area.height {
        let begin = (y as usize * frame.width as usize + left as usize) * 4;
        pixels.extend_from_slice(&frame.rgba[begin..begin + area.width as usize * 4]);
    }
    Some(pixels)
}
