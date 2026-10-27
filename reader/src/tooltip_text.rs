//! A bounded second look at an already located name line, never a scene text search.
use image::{GrayImage,Luma,imageops::FilterType};
use minerva_core::{Frame,ScreenPoint};
use serde_json::Value;

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
                let p=&frame.rgba[at..at+3];let (r,g,b)=(i32::from(p[0]),i32::from(p[1]),i32::from(p[2]));
                let neutral=(r-g).abs()<55 && b-r<100;
                let luma=(r*30+g*59+b*11)/100;
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
