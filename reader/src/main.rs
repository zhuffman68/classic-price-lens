//! Pixel-only bridge: accepts captured RGBA or PNG paths; no game resources.
#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]
use minerva_core::{
    Frame, ItemCapture, ItemTooltipReader, PlayerShopReader, ScreenPoint, ShopCapture,
};
use serde::Deserialize;
use std::io::{self, BufRead, Write};
use std::time::Instant;
mod experience;
mod game_area;
use game_area::{Locator, Rect};

#[derive(Deserialize)]
struct Request {
    path: String,
    #[serde(default)]
    at_ms: u64,
    pointer: Option<ScreenPoint>,
    width: Option<u32>,
    height: Option<u32>,
    #[serde(default)]
    tooltip: bool,
    origin: Option<ScreenPoint>,
    #[serde(default)]
    auto_game: bool,
    #[serde(default)]
    locate_only: bool,
    roi: Option<Rect>,
    #[serde(default)]
    experience_only: bool,
    #[serde(default)]
    read_map: bool,
}

fn main() {
    let mut reader = None;
    let mut tooltip_reader = None;
    let mut locator = Locator::new();
    let mut experience = None;
    let stdin = io::stdin();
    let mut stdout = io::BufWriter::new(io::stdout());
    for line in stdin.lock().lines() {
        let result = (|| -> Result<serde_json::Value, Box<dyn std::error::Error>> {
            let request: Request = serde_json::from_str(&line?)?;
            let started = Instant::now();
            let frame = if let (Some(width), Some(height)) = (request.width, request.height) {
                if width == 0
                    || height == 0
                    || width > 16384
                    || height > 16384
                    || u64::from(width) * u64::from(height) > 16_777_216
                {
                    return Err("capture dimensions exceed limit".into());
                }
                let rgba = std::fs::read(&request.path)?;
                if rgba.len() != width as usize * height as usize * 4 {
                    return Err("captured RGBA length does not match dimensions".into());
                }
                Frame {
                    width,
                    height,
                    rgba,
                    at_ms: request.at_ms,
                }
            } else if request.width.is_some() || request.height.is_some() {
                return Err("raw captures require both width and height".into());
            } else {
                let img = image::open(&request.path)?.into_rgba8();
                if img.width() > 16384 || img.height() > 16384 {
                    return Err("capture dimensions exceed limit".into());
                }
                Frame {
                    width: img.width(),
                    height: img.height(),
                    rgba: img.into_raw(),
                    at_ms: request.at_ms,
                }
            };
            let mut origin = request.origin.unwrap_or(ScreenPoint { x: 0, y: 0 });
            let mut location = None;
            let frame = if request.auto_game || request.locate_only {
                let image = image::RgbaImage::from_raw(frame.width, frame.height, frame.rgba)
                    .ok_or("invalid pixels")?;
                location = locator.find(&image);
                if location.is_none() || request.locate_only {
                    return Ok(
                        serde_json::json!({"atMs":request.at_ms,"shop":null,"hover":null,"tooltip":null,
                        "gameArea":location.as_ref().map(|l|l.area),"gameGuards":location.as_ref().map(|l|&l.guards),
                        "ocrMs":started.elapsed().as_secs_f64()*1000.0}),
                    );
                }
                let mut area = location.as_ref().unwrap().area;
                if let Some(roi) = request.roi {
                    let x = area.x.max(roi.x);
                    let y = area.y.max(roi.y);
                    let right = (area.x + area.width).min(roi.x + roi.width);
                    let bottom = (area.y + area.height).min(roi.y + roi.height);
                    if right > x && bottom > y {
                        area = Rect {
                            x,
                            y,
                            width: right - x,
                            height: bottom - y,
                        };
                    }
                }
                origin.x += area.x as i32;
                origin.y += area.y as i32;
                let cropped =
                    image::imageops::crop_imm(&image, area.x, area.y, area.width, area.height)
                        .to_image();
                Frame {
                    width: area.width,
                    height: area.height,
                    rgba: cropped.into_raw(),
                    at_ms: request.at_ms,
                }
            } else {
                frame
            };
            if request.experience_only {
                let result = experience
                    .get_or_insert_with(experience::ExperienceReader::new)
                    .read(frame, origin, request.read_map);
                return Ok(serde_json::json!({"atMs":request.at_ms,"experience":result,
                    "experienceOnly":true,"ocrMs":started.elapsed().as_secs_f64()*1000.0}));
            }
            let capture = ShopCapture {
                frame,
                origin,
                pointer: request.pointer,
            };
            let mut value = serde_json::to_value(
                reader
                    .get_or_insert_with(PlayerShopReader::bundled)
                    .read(&capture),
            )?;
            if request.tooltip {
                if let Some(pointer) = request.pointer {
                    let tooltip_capture = ItemCapture {
                        frame: capture.frame,
                        origin: capture.origin,
                        pointer,
                    };
                    let reading = tooltip_reader
                        .get_or_insert_with(ItemTooltipReader::bundled)
                        .read(&tooltip_capture);
                    value["tooltip"] = serde_json::to_value(reading.tooltip)?;
                }
            }
            value["ocrMs"] = serde_json::json!(started.elapsed().as_secs_f64() * 1000.0);
            value["gameArea"] = serde_json::to_value(location.as_ref().map(|l| l.area))?;
            value["gameGuards"] = serde_json::to_value(location.as_ref().map(|l| &l.guards))?;
            Ok(value)
        })();
        let value = result.unwrap_or_else(|err| serde_json::json!({"error":err.to_string()}));
        if writeln!(stdout, "{value}")
            .and_then(|_| stdout.flush())
            .is_err()
        {
            break;
        }
    }
}
