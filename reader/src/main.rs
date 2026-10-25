//! Pixel-only bridge: accepts captured RGBA or PNG paths; no game resources.
#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]
use minerva_core::{Frame, PlayerShopReader, ScreenPoint, ShopCapture, ItemCapture, ItemTooltipReader};
use serde::Deserialize;
use std::io::{self, BufRead, Write};
use std::time::Instant;

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
}

fn main() {
    let mut reader = PlayerShopReader::bundled();
    let mut tooltip_reader = None;
    let stdin = io::stdin();
    let mut stdout = io::BufWriter::new(io::stdout());
    for line in stdin.lock().lines() {
        let result = (|| -> Result<serde_json::Value, Box<dyn std::error::Error>> {
            let request: Request = serde_json::from_str(&line?)?;
            let started = Instant::now();
            let frame = if let (Some(width), Some(height)) = (request.width, request.height) {
                if width == 0 || height == 0 || width > 16384 || height > 16384 || u64::from(width) * u64::from(height) > 16_777_216 {
                    return Err("capture dimensions exceed limit".into());
                }
                let rgba = std::fs::read(&request.path)?;
                if rgba.len() != width as usize * height as usize * 4 {
                    return Err("captured RGBA length does not match dimensions".into());
                }
                Frame { width, height, rgba, at_ms: request.at_ms }
            } else if request.width.is_some() || request.height.is_some() {
                return Err("raw captures require both width and height".into());
            } else {
                let img = image::open(&request.path)?.into_rgba8();
                if img.width() > 16384 || img.height() > 16384 {
                    return Err("capture dimensions exceed limit".into());
                }
                Frame { width: img.width(), height: img.height(), rgba: img.into_raw(), at_ms: request.at_ms }
            };
            let capture = ShopCapture { frame, origin: request.origin.unwrap_or(ScreenPoint { x: 0, y: 0 }), pointer: request.pointer };
            let mut value = serde_json::to_value(reader.read(&capture))?;
            if request.tooltip {
                if let Some(pointer) = request.pointer {
                    let tooltip_capture = ItemCapture { frame: capture.frame, origin: capture.origin, pointer };
                    let reading = tooltip_reader.get_or_insert_with(ItemTooltipReader::bundled).read(&tooltip_capture);
                    value["tooltip"] = serde_json::to_value(reading.tooltip)?;
                }
            }
            value["ocrMs"] = serde_json::json!(started.elapsed().as_secs_f64() * 1000.0);
            Ok(value)
        })();
        let value = result.unwrap_or_else(|err| serde_json::json!({"error":err.to_string()}));
        if writeln!(stdout, "{value}").and_then(|_| stdout.flush()).is_err() { break; }
    }
}
