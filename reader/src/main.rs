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
mod text;
mod pickups;
mod tooltip_text;
mod tooltip_surface;
mod tooltip_association;
mod centered_tooltip;
mod shop_prices;
mod shop_selection;
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
    #[serde(default)]
    tooltip_retry: bool,
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
    #[serde(default)]
    pickups_only: bool,
    #[serde(default)]
    exclude: Vec<Rect>,
}

fn main() {
    let mut reader = None;
    let mut tooltip_reader = None;
    let mut centered_titles = centered_tooltip::CenteredTitles::default();
    let mut tooltip_association = tooltip_association::Selector::default();
    let mut locator = Locator::new();
    let mut experience = None;
    let mut pickups = pickups::PickupLogReader::default();
    let mut price_recovery = shop_prices::PriceRecovery::default();
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
                        "gameFooter":location.as_ref().map(|l|l.footer),
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
            if request.pickups_only {
                return Ok(serde_json::json!({"atMs":request.at_ms,"pickups":pickups.read(&frame),
                    "pickupsRead":true,"ocrMs":started.elapsed().as_secs_f64()*1000.0}));
            }
            let mut frame=frame;
            mask_owned_surfaces(&mut frame,origin,&request.exclude);
            let capture = ShopCapture {
                frame,
                origin,
                pointer: request.pointer,
            };
            let shop_reader=reader.get_or_insert_with(PlayerShopReader::bundled);
            let mut shop_reading=shop_reader.read(&capture);
            price_recovery.apply(&capture,&mut shop_reading,shop_reader);
            let mut value = serde_json::to_value(shop_reading)?;
            if request.tooltip {
                if let Some(pointer) = request.pointer {
                    let mut tooltip_capture = ItemCapture {
                        frame: capture.frame,
                        origin: capture.origin,
                        pointer,
                    };
                    let (prepared,markers)=tooltip_surface::prepare(&tooltip_capture.frame);
                    if let Some(frame)=prepared {tooltip_capture.frame=frame}
                    let scale_hint=location.as_ref().and_then(|l|l.guards.get(1)).map(|r|r.width as f32/36.0);
                    let association=tooltip_association.select(&tooltip_capture,&markers,scale_hint);
                    value["tooltipAssociation"]=association.metadata;
                    if association.rejected {
                        value["tooltip"]=serde_json::json!("none");
                    } else {
                    if let Some(rect)=association.panel {
                        let mut rgba=Vec::with_capacity((rect.w*rect.h*4) as usize);
                        for y in rect.y..rect.y+rect.h {
                            let start=((y*tooltip_capture.frame.width+rect.x)*4) as usize;
                            rgba.extend_from_slice(&tooltip_capture.frame.rgba[start..start+(rect.w*4) as usize]);
                        }
                        tooltip_capture.frame=Frame{width:rect.w,height:rect.h,rgba,at_ms:tooltip_capture.frame.at_ms};
                        tooltip_capture.origin.x+=rect.x as i32;
                        tooltip_capture.origin.y+=rect.y as i32;
                        // This is only an internal captured-pixel probe, like
                        // the existing popup reader. The OS pointer is never
                        // moved; source/slot metadata retains its real proof.
                        tooltip_capture.pointer=ScreenPoint{x:tooltip_capture.origin.x+(rect.w.min(32)/2) as i32,y:tooltip_capture.origin.y+(rect.h.min(40)/2) as i32};
                    }
                    let tooltip_reader=tooltip_reader.get_or_insert_with(ItemTooltipReader::bundled);
                    let reading = tooltip_reader.read(&tooltip_capture);
                    value["tooltip"] = serde_json::to_value(reading.tooltip)?;
                    let mut marker_title=true;
                    if !value["tooltip"]["found"]["name"].is_string() {
                        let popup=if let Some(title)=centered_titles.read(&tooltip_capture) {
                            marker_title=false;
                            Some(title)
                        } else {
                            tooltip_text::popup(tooltip_reader,&mut tooltip_capture)
                        };
                        if let Some(popup)=popup {
                            value["tooltip"]=serde_json::to_value(popup)?;
                            value["tooltip"]["found"]["pinned"]=serde_json::json!(true);
                        }
                    }
                    if request.tooltip_retry {
                        let found=&value["tooltip"]["found"];
                        if found.is_object() {
                            let candidates=tooltip_text::alternatives(&tooltip_capture.frame,tooltip_capture.origin,found,marker_title);
                            value["tooltip"]["found"]["alternatives"]=serde_json::json!(candidates);
                        }
                        value["tooltipRetried"]=serde_json::json!(true);
                    }
                    }
                }
            }
            value["ocrMs"] = serde_json::json!(started.elapsed().as_secs_f64() * 1000.0);
            value["gameArea"] = serde_json::to_value(location.as_ref().map(|l| l.area))?;
            value["gameGuards"] = serde_json::to_value(location.as_ref().map(|l| &l.guards))?;
            value["gameFooter"] = serde_json::to_value(location.as_ref().map(|l| l.footer))?;
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

fn mask_owned_surfaces(frame: &mut Frame, origin: ScreenPoint, regions: &[Rect]) {
    // Only independent Lupin editor surfaces are supplied. Locator proofs were
    // read from the original capture; the editor must never cover those proofs.
    for rect in regions.iter().take(8) {
        let left=(i64::from(rect.x)-i64::from(origin.x)).clamp(0,i64::from(frame.width)) as u32;
        let top=(i64::from(rect.y)-i64::from(origin.y)).clamp(0,i64::from(frame.height)) as u32;
        let right=(i64::from(rect.x)+i64::from(rect.width)-i64::from(origin.x)).clamp(0,i64::from(frame.width)) as u32;
        let bottom=(i64::from(rect.y)+i64::from(rect.height)-i64::from(origin.y)).clamp(0,i64::from(frame.height)) as u32;
        for y in top..bottom {
            for x in left..right {
                let at=((y*frame.width+x)*4) as usize;
                frame.rgba[at..at+4].copy_from_slice(&[0,0,0,255]);
            }
        }
    }
}

#[cfg(test)]
mod writer_mask_tests {
    use super::*;

    #[test]
    fn masks_only_owned_pixels_with_a_nonzero_roi_origin() {
        let mut frame=Frame{width:10,height:8,rgba:vec![200;10*8*4],at_ms:0};
        mask_owned_surfaces(&mut frame,ScreenPoint{x:30,y:40},&[
            Rect{x:33,y:42,width:3,height:2},Rect{x:0,y:0,width:2,height:2},
        ]);
        for y in 0..8 {
            for x in 0..10 {
                let at=(y*10+x)*4;
                assert_eq!(&frame.rgba[at..at+4],if (3..6).contains(&x) && (2..4).contains(&y) {&[0,0,0,255]} else {&[200;4]});
            }
        }
    }

    #[test]
    fn clips_large_rectangles_to_the_capture() {
        let mut frame=Frame{width:3,height:2,rgba:vec![200;3*2*4],at_ms:0};
        mask_owned_surfaces(&mut frame,ScreenPoint{x:50,y:60},&[Rect{x:0,y:0,width:u32::MAX,height:u32::MAX}]);
        assert!(frame.rgba.chunks(4).all(|pixel|pixel==[0,0,0,255]));
    }
}
