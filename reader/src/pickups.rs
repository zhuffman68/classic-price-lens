//! Reads only a caller-supplied, bounded crop of the visible pickup log.
use image::{GrayImage, Luma, RgbaImage};
use minerva_core::Frame;
use serde_json::{Value, json};
use std::collections::HashMap;

#[derive(Default)]
pub struct PickupLogReader { cache:HashMap<(u32,u32,Vec<u8>),Option<(String,Option<u32>)>> }

fn amount(text:&str)->Option<u32> {
    if text.is_empty() || !text.bytes().all(|b|b.is_ascii_digit()||b==b',') {return None}
    let groups=text.split(',').collect::<Vec<_>>();
    if groups.len()>1 && (groups[0].is_empty() || groups[0].len()>3 || groups[1..].iter().any(|s|s.len()!=3)) {return None}
    let digits=text.replace(',',"");
    if digits.len()>1 && digits.starts_with('0') {return None}
    let n=digits.parse::<u32>().ok()?;(n>0 && n<=2_147_483_647).then_some(n)
}

fn message(text:&str)->Option<(String,Option<u32>)> {
    let text=text.trim().trim_end_matches('.').split_whitespace().collect::<Vec<_>>().join(" ").to_ascii_lowercase();
    if let Some(n)=text.strip_prefix("you have gained mesos (+").and_then(|s|s.strip_suffix(')')) {
        let n=amount(n)?;return Some((format!("mesos:{n}"),Some(n)))
    }
    // Other complete system lines can anchor scrolling, but never add income.
    if text.starts_with("you have gained experience (+") && text.ends_with(')') {
        let n=text.strip_prefix("you have gained experience (+")?.strip_suffix(')')?;
        amount(n)?;return Some((text,None))
    }
    None
}

fn ink(image:&RgbaImage,x:u32,y:u32)->bool {
    let p=image.get_pixel(x,y).0;
    if p[0]<160 || p[1]<155 || p[2]<95 || p[0].abs_diff(p[1])>65 {return false}
    // System text has a dark outline. Flat panels and bright scenery aren't ink.
    for dy in -2i32..=2 {for dx in -2i32..=2 {
        let nx=x as i32+dx;let ny=y as i32+dy;
        if nx<0 || ny<0 || nx>=image.width() as i32 || ny>=image.height() as i32 {continue}
        let q=image.get_pixel(nx as u32,ny as u32).0;
        if q[0]<65 && q[1]<65 && q[2]<65 {return true}
    }}
    false
}

impl PickupLogReader {
    pub fn read(&mut self,frame:&Frame)->Value {
        if !(180..=720).contains(&frame.width) || !(40..=340).contains(&frame.height) {return json!({"valid":false,"lines":[]})}
        let Some(image)=RgbaImage::from_raw(frame.width,frame.height,frame.rgba.clone()) else {return json!({"valid":false,"lines":[]})};
        let mask=GrayImage::from_fn(frame.width,frame.height,|x,y|Luma([if ink(&image,x,y){0}else{255}]));
        let mut bands=Vec::new();let mut y=0;
        while y<frame.height {
            if (0..frame.width).filter(|&x|mask.get_pixel(x,y).0[0]==0).count()<3 {y+=1;continue}
            let top=y;let mut bottom=y+1;let mut blank=0;y+=1;
            while y<frame.height && blank<3 {
                if (0..frame.width).filter(|&x|mask.get_pixel(x,y).0[0]==0).count()>=2 {bottom=y+1;blank=0}else{blank+=1}
                y+=1;
            }
            if (7..=25).contains(&(bottom-top)) {bands.push((top,bottom))}
        }
        let mut rows=Vec::new();let mut calls=0;
        for (top,bottom) in bands.into_iter().rev().take(24).collect::<Vec<_>>().into_iter().rev() {
            let columns=(0..frame.width).filter(|&x|(top..bottom).any(|y|mask.get_pixel(x,y).0[0]==0)).collect::<Vec<_>>();
            if columns.is_empty(){continue}
            let mut starts=vec![columns[0]];
            for pair in columns.windows(2) {if pair[1]-pair[0]>=15 {starts.push(pair[1])}}
            // Examine complete outlined text runs, never a numeric tail alone.
            let right=*columns.last().unwrap()+1;let mut found=None;
            for left in starts.into_iter().rev() {
                let width=right-left;if !(155..=600).contains(&width){continue}
                let patch=image::imageops::crop_imm(&mask,left,top,width,bottom-top).to_image();
                let key=(patch.width(),patch.height(),patch.as_raw().clone());
                let value=if let Some(value)=self.cache.get(&key){value.clone()} else {
                    if calls>=12 {return json!({"valid":false,"lines":[]})} calls+=1;
                    let value=crate::text::read(&patch).and_then(|text|message(&text));
                    if self.cache.len()>=128 {self.cache.clear()}
                    self.cache.insert(key,value.clone());value
                };
                if value.is_some(){found=value;break}
            }
            if let Some((key,mesos))=found {rows.push(json!({"key":key,"mesos":mesos}))}
        }
        json!({"valid":true,"lines":rows})
    }
}

#[cfg(test)]
mod tests {
    use super::message;
    #[test] fn counts_only_complete_literal_pickup_lines() {
        assert_eq!(message("You have gained mesos (+29)."),Some(("mesos:29".into(),Some(29))));
        assert_eq!(message("You have gained mesos (+2,500,000)"),Some(("mesos:2500000".into(),Some(2_500_000))));
        for text in ["29", "You have gained mesos (+2.5m)", "You have gained mesos (+2,50)","Player: You have gained mesos (+29)","You have gained mesos (-29)","You have gained mesos (+2147483648)"] {assert_eq!(message(text),None,"{text}")}
        assert_eq!(message("You have gained experience (+150)"),Some(("you have gained experience (+150)".into(),None)));
    }
}
