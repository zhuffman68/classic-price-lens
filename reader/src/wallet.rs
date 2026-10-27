//! Inventory wallet only: framed white counter, adjacent coin, literal Mesos label.
//! Never reads shop listings or infers a balance while the wallet is hidden.
use image::{GrayImage, Luma, RgbaImage};
use minerva_core::{Frame, ScreenPoint};
use serde_json::{Value, json};
use std::collections::HashMap;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Field { x:u32, y:u32, w:u32, h:u32 }

#[derive(Default)]
pub struct WalletReader {
    previous: Option<(Field, ScreenPoint, Vec<u8>, Value)>,
    labels: HashMap<(u32,u32,Vec<u8>),bool>,
}

fn white(p: &[u8]) -> bool { p[0]>=230 && p[1]>=230 && p[2]>=230 }
fn yellow(p: &[u8]) -> bool { p[0]>165 && p[1]>130 && p[2]<115 && p[0]>p[2]+50 }

impl WalletReader {
    pub fn read(&mut self, frame:&Frame, origin:ScreenPoint) -> Value {
        let Some(image) = RgbaImage::from_raw(frame.width,frame.height,frame.rgba.clone()) else {return Value::Null};
        let mut fields = Vec::new();
        for y in 1..image.height().saturating_sub(10) {
            let mut x = 1;
            while x < image.width() {
                if !white(&image.get_pixel(x,y).0) {x+=1;continue}
                let left=x;
                while x<image.width() && white(&image.get_pixel(x,y).0) {x+=1}
                let width=x-left;
                if !(65..=380).contains(&width) || x+24>=image.width() {continue}
                // A field's first blank interior row lies immediately below a dark rim.
                if white(&image.get_pixel(left+width/2,y-1).0) {continue}
                let mut height=1;
                while y+height<image.height() && height<=32 {
                    let count=(left..x).filter(|&col| white(&image.get_pixel(col,y+height).0)).count();
                    if count*100<(width as usize)*68 {break}
                    height+=1;
                }
                if !(8..=28).contains(&height) {continue}
                // Inventory footer: small yellow coin inside the same field on the left.
                let coin_left=left.saturating_sub(height*2+3);
                let coins=(y..y+height).flat_map(|row|(coin_left..left+height.min(width)).map(move |col|(col,row)))
                    .filter(|&(col,row)| yellow(&image.get_pixel(col,row).0)).count();
                if coins<8 {continue}
                let field=Field{x:left,y,w:width,h:height};
                if !fields.iter().any(|f:&Field| f.x.abs_diff(left)<4 && f.y.abs_diff(y)<4) {fields.push(field)}
                if fields.len()>=6 {break}
            }
            if fields.len()>=6 {break}
        }
        let mut readings=Vec::new();
        for field in fields {
            let label_pad=(field.h/4).max(1);
            let label_w=(field.h*5/2).min(image.width()-field.x-field.w-label_pad);
            let patch=image::imageops::crop_imm(&image,field.x,field.y,field.w+label_pad+label_w,field.h).to_image();
            let bytes=patch.as_raw();
            if let Some((old,old_origin,old_pixels,value))=&self.previous {
                if *old==field && old_origin.x==origin.x && old_origin.y==origin.y && old_pixels==bytes {
                    let mut value=value.clone();value["cached"]=json!(true);readings.push(value);continue
                }
            }
            let mut label=GrayImage::from_fn(label_w,field.h,|x,y| {
                let p=image.get_pixel(field.x+field.w+label_pad+x,field.y+y).0;
                Luma([if p[0]>180 && p[1]>180 && p[2]>180 {0} else {255}])
            });
            // A white frame or neighboring panel is not part of the label.
            for x in 0..label_w {
                if (0..field.h).filter(|&y|label.get_pixel(x,y).0[0]==0).count()*10>field.h as usize*8 {
                    for y in 0..field.h {label.put_pixel(x,y,Luma([255]));}
                }
            }
            let label_key=(label.width(),label.height(),label.as_raw().clone());
            let valid=match self.labels.get(&label_key) {
                Some(valid)=>*valid,
                None=> {
                    let valid=crate::text::read(&label).is_some_and(|name|name.trim().eq_ignore_ascii_case("mesos"));
                    if self.labels.len()>=64 {self.labels.clear();}
                    self.labels.insert(label_key,valid);valid
                }
            };
            if !valid {continue}
            let number=GrayImage::from_fn(field.w,field.h,|x,y| {
                let p=image.get_pixel(field.x+x,field.y+y).0;
                Luma([if p[0]<135 && p[1]<135 && p[2]<135 {0} else {255}])
            });
            let Some(text)=crate::text::read(&number) else {continue};
            let Some(mesos)=parse_amount(&text) else {continue};
            let value=json!({"mesos":mesos,"cached":false,
                "area":{"x":origin.x+field.x as i32,"y":origin.y+field.y as i32,"width":field.w,"height":field.h}});
            self.previous=Some((field,origin,bytes.clone(),value.clone()));
            readings.push(value);
        }
        let Some(first)=readings.first() else {self.previous=None;return Value::Null};
        if readings.iter().any(|r|r["mesos"]!=first["mesos"]) {return Value::Null}
        first.clone()
    }
}

fn parse_amount(text:&str)->Option<u32> {
    let text=text.trim();
    if text.is_empty() || !text.chars().all(|c|c.is_ascii_digit()||c==',') {return None}
    let groups=text.split(',').collect::<Vec<_>>();
    if groups.len()>1 && (groups[0].is_empty() || groups[0].len()>3 || groups[1..].iter().any(|s|s.len()!=3)) {return None}
    let digits=text.replace(',',"");
    if digits.len()>1 && digits.starts_with('0') {return None}
    let value=digits.parse::<u32>().ok()?;
    (value<=2_147_483_647).then_some(value)
}

#[cfg(test)]
mod tests {
    use super::parse_amount;
    #[test] fn strict_whole_meso_amounts() {
        for (text,value) in [("0",0),("2,121",2121),("2147483647",2147483647)] {assert_eq!(parse_amount(text),Some(value))}
        for text in ["2.121","2,12","2I21","0021","2147483648","-2","3k"] {assert_eq!(parse_amount(text),None)}
    }
}
