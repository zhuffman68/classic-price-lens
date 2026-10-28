//! Adapt a selected band's measured background to the pinned reader's palette.
//! Only a broad orange band inside an independently detected shop is eligible.
use minerva_core::{Frame,ScreenRect,ShopCapture,ShopList,ShopRow};
use std::collections::HashMap;

const BLUE:[f32;3]=[202.0,213.0,223.0];
const ORANGE:[f32;3]=[251.0,167.0,46.0];

pub struct Plan {
    pub key:Vec<u8>,
    pub area:ScreenRect,
    x0:u32,x1:u32,y0:u32,y1:u32,
    source:[u8;3],target:[u8;3],
}

fn brightness(p:[u8;3],base:[f32;3])->Option<f32> {
    let k=(0..3).map(|i|p[i] as f32*base[i]).sum::<f32>()/base.iter().map(|v|v*v).sum::<f32>();
    ((0.45..=1.15).contains(&k) && (0..3).all(|i|(p[i] as f32-base[i]*k).abs()<=7.0)).then_some(k)
}

fn pixel(frame:&Frame,x:u32,y:u32)->[u8;3] {
    let i=((y*frame.width+x)*4) as usize;
    [frame.rgba[i],frame.rgba[i+1],frame.rgba[i+2]]
}

pub fn plan(capture:&ShopCapture,shop:&ShopList)->Option<Plan> {
    let frame=&capture.frame;
    let width=shop.rows.first().map(|r|r.area.width)
        .unwrap_or((shop.area.width as f32*253.0/311.0).round() as u32);
    if !(140..=480).contains(&width) {return None}
    let x=shop.rows.first().map(|r|r.area.x)
        .unwrap_or(shop.area.x+shop.area.width as i32-width as i32);
    let x0=(x as i64-capture.origin.x as i64).clamp(0,frame.width as i64) as u32;
    let x1=(x0+width).min(frame.width);
    let pitch=(width as f32*62.6/253.0).round() as i64;
    let y0=(shop.area.y as i64-capture.origin.y as i64-pitch-2).clamp(0,frame.height as i64) as u32;
    let y1=(shop.area.bottom()-capture.origin.y as i64+pitch+2).clamp(0,frame.height as i64) as u32;
    if x1-x0!=width || y1<=y0 || u64::from(width)*u64::from(y1-y0)>1_000_000 {return None}
    let mut blues=HashMap::new();
    let mut bands:Vec<Vec<(u32,[u8;3],usize)>>=Vec::new();
    for y in y0..y1 {
        let mut orange=HashMap::new();let mut count=0;
        for x in x0..x1 {
            let p=pixel(frame,x,y);
            if brightness(p,BLUE).is_some() {*blues.entry(p).or_insert(0usize)+=1}
            if brightness(p,ORANGE).is_some() {*orange.entry(p).or_insert(0usize)+=1;count+=1}
        }
        if count*5<width as usize*3 {continue}
        let (colour,n)=orange.into_iter().max_by_key(|&(p,n)|(n,p))?;
        if bands.last().and_then(|b|b.last()).is_none_or(|r|y-r.0>3) {bands.push(Vec::new())}
        bands.last_mut()?.push((y,colour,n));
    }
    let height=width as f32*54.0/253.0;
    let mut valid=bands.into_iter().filter(|b| {
        let h=(b.last().unwrap().0-b[0].0+1) as f32;
        h>=height*0.65 && h<=height*1.4 && b.len() as f32>=height*0.45
    });
    let band=valid.next()?;
    if valid.next().is_some() {return None}
    let mut colours=HashMap::new();
    for &(_,p,n) in &band {*colours.entry(p).or_insert(0usize)+=n}
    let (source,_)=colours.into_iter().max_by_key(|&(p,n)|(n,p))?;
    let (normal,_)=blues.into_iter().max_by_key(|&(p,n)|(n,p))?;
    let k=brightness(normal,BLUE)?;
    let target=ORANGE.map(|v|(v*k).round().clamp(0.0,255.0) as u8);
    if (0..3).all(|i|source[i].abs_diff(target[i])<=8) {return None}
    let top=band[0].0;let bottom=band.last()?.0+1;
    let area=ScreenRect{x,y:top as i32+capture.origin.y,width,height:bottom-top};
    if shop.rows.iter().any(|r|r.name.is_some() && r.price.is_some() && !r.covered && in_band(area,r)) {return None}
    // Include the complete surrounding list and pictures, plus coordinates:
    // text, page, movement and occluder changes cannot reuse another result.
    let left=x0.saturating_sub((width as f32*58.0/253.0).ceil() as u32);
    let key_top=((shop.area.y as i64-capture.origin.y as i64).clamp(y0 as i64,y1 as i64) as u32).min(top);
    let key_bottom=((shop.area.bottom()-capture.origin.y as i64).clamp(y0 as i64,y1 as i64) as u32).max(bottom);
    let mut key=Vec::new();
    for value in [x,capture.origin.y+key_top as i32,width as i32,(key_bottom-key_top) as i32] {key.extend_from_slice(&value.to_le_bytes())}
    for y in key_top..key_bottom {
        key.extend_from_slice(&frame.rgba[((y*frame.width+left)*4) as usize..((y*frame.width+x1)*4) as usize]);
    }
    Some(Plan{key,area,x0,x1,y0:top,y1:bottom,source,target})
}

pub fn in_band(band:ScreenRect,row:&ShopRow)->bool {
    let centre=row.area.y as i64+row.area.height as i64/2;
    row.area.x.abs_diff(band.x)<=3 && row.area.width.abs_diff(band.width)<=3
        && centre>=band.y as i64 && centre<band.bottom()
}

impl Plan {
    pub fn corrected(&self,capture:&ShopCapture)->ShopCapture {
        let mut frame=capture.frame.clone();
        for y in self.y0..self.y1 {
            for x in self.x0..self.x1 {
                let p=pixel(&frame,x,y);
                if (0..3).all(|i|p[i].abs_diff(self.source[i])<=2) {
                    let at=((y*frame.width+x)*4) as usize;
                    frame.rgba[at..at+3].copy_from_slice(&self.target);
                }
            }
        }
        ShopCapture{frame,origin:capture.origin,pointer:None}
    }
}
