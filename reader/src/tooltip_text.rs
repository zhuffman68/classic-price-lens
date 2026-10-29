//! A bounded second look at an already located name line, never a scene text search.
use image::{GrayImage,Luma,imageops::FilterType};
use minerva_core::{Frame,ScreenPoint,ItemCapture,ItemTooltip,ItemTooltipReader};
use serde_json::Value;

/// A clicked item link can open its description far from the pointer. Probe
/// captured pixels only; the UI also validates its name and description panel.
pub fn popup(reader:&ItemTooltipReader,capture:&mut ItemCapture)->Option<ItemTooltip> {
    let original=capture.pointer;
    let centers=|length:u32|->Vec<i32> {
        if length<=1280 {return vec![(length/2) as i32]}
        let mut points:Vec<i32>=(640..length).step_by(1280).map(|x|x as i32).collect();
        let end=length.saturating_sub(640) as i32;
        if points.last().copied()!=Some(end) {points.push(end)}
        points
    };
    let mut result=None;
    'search:for y in centers(capture.frame.height).into_iter().take(3) {
        for x in centers(capture.frame.width).into_iter().take(3) {
            capture.pointer=ScreenPoint{x:x+capture.origin.x,y:y+capture.origin.y};
            let candidate=reader.read(capture).tooltip;
            if matches!(&candidate,ItemTooltip::Found{name:Some(_),..}) {result=Some(candidate);break 'search}
        }
    }
    capture.pointer=original;result
}

pub fn alternatives(frame:&Frame,origin:ScreenPoint,found:&Value)->Vec<String> {
    let read = || -> Option<Vec<String>> {
        let area=found.get("area")?;
        let x=area["x"].as_i64()?.checked_sub(i64::from(origin.x))?;
        let y=area["y"].as_i64()?.checked_sub(i64::from(origin.y))?;
        let w=area["width"].as_u64()? as u32;
        let h=area["height"].as_u64()? as u32;
        if x<0 || y<0 || !(40..=720).contains(&w) || !(8..=32).contains(&h)
            || x as u32+w>frame.width || y as u32+h>frame.height {return None}
        let mut results=Vec::new();
        for (threshold,scale,filter) in [(None,3,FilterType::Triangle),(Some(150),2,FilterType::Triangle)] {
            let ink=GrayImage::from_fn(w,h,|col,row| {
                let at=(((y as u32+row)*frame.width+x as u32+col)*4) as usize;
                let p=&frame.rgba[at..at+3];let light=crate::tooltip_surface::title_light([p[0],p[1],p[2]]);
                let neutral=light.is_some();let luma=i32::from(light.unwrap_or(0));
                let value=match threshold {
                    Some(t)=> if neutral && luma>=t {0} else {255},
                    None=> if neutral {255-((luma-100)*255/120).clamp(0,255)} else {255}
                };
                Luma([value as u8])
            });
            if let Some(text)=crate::text::read_scaled(&ink,scale,filter) {
                if !results.contains(&text) {results.push(text)}
            }
        }
        Some(results)
    };
    read().unwrap_or_default()
}
