//! Retry unread prices through the existing strict shop reader at two resamplings.
//! Never infer a number, relax its parser, or replace an already-read price.
use image::{RgbaImage,imageops::{self,FilterType}};
use minerva_core::{Frame,ListedPrice,PlayerShopReader,ScreenPoint,ShopCapture,ShopReading};
use std::collections::HashMap;

type Recovered = Vec<(i32,String,ListedPrice)>;

#[derive(Default)]
pub struct PriceRecovery {
    reader: Option<PlayerShopReader>,
    // Include the whole shop patch: another row's tooltip can change detection.
    cache: HashMap<Vec<u8>,Recovered>,
}

impl PriceRecovery {
    pub fn apply(&mut self,capture:&ShopCapture,reading:&mut ShopReading) {
        let Some(shop)=reading.shop.as_mut() else {return};
        if !shop.rows.iter().any(|r|!r.covered && r.name.is_some() && r.price.is_none()) {return}
        let frame=&capture.frame;
        let x=(shop.area.x-capture.origin.x-8).max(0) as u32;
        let y=(shop.area.y-capture.origin.y-8).max(0) as u32;
        let right=(shop.area.x as i64-capture.origin.x as i64+shop.area.width as i64+8).clamp(0,frame.width as i64) as u32;
        let bottom=shop.rows.iter().map(|r|r.area.y as i64-capture.origin.y as i64+r.area.height as i64+8)
            .max().unwrap_or(0).clamp(0,frame.height as i64) as u32;
        if right<=x || bottom<=y || u64::from(right-x)*u64::from(bottom-y)>1_000_000 {return}
        let Some(image)=RgbaImage::from_raw(frame.width,frame.height,frame.rgba.clone()) else {return};
        let patch=imageops::crop_imm(&image,x,y,right-x,bottom-y).to_image();
        let mut key=Vec::with_capacity(patch.as_raw().len()+8);
        key.extend_from_slice(&patch.width().to_le_bytes());key.extend_from_slice(&patch.height().to_le_bytes());
        key.extend_from_slice(patch.as_raw());
        let values=if let Some(values)=self.cache.get(&key) {values.clone()} else {
            let reader=self.reader.get_or_insert_with(PlayerShopReader::bundled);
            let mut attempts=Vec::new();
            for filter in [FilterType::Triangle,FilterType::CatmullRom] {
                let scaled=imageops::resize(&patch,patch.width()*2,patch.height()*2,filter);
                let retry=ShopCapture {frame:Frame {width:scaled.width(),height:scaled.height(),rgba:scaled.into_raw(),at_ms:frame.at_ms},
                                      origin:ScreenPoint{x:0,y:0},pointer:None};
                let rows=reader.read(&retry).shop.map(|s|s.rows).unwrap_or_default();
                attempts.push(rows.into_iter().filter(|r|!r.covered).filter_map(|r|Some((r.area.y/2,r.name?,r.price?))).collect::<Recovered>());
            }
            let values=consensus(&attempts[0],&attempts[1]);
            if self.cache.len()>=8 {self.cache.clear();}
            self.cache.insert(key,values.clone());values
        };
        for row in &mut shop.rows {
            if row.covered || row.price.is_some() {continue}
            let local_y=row.area.y-capture.origin.y-y as i32;
            if let Some((_,_,price))=values.iter().find(|(top,name,_)|top.abs_diff(local_y)<=3 && row.name.as_ref()==Some(name)) {
                row.price=Some(*price);
            }
        }
    }
}

fn consensus(first:&Recovered,second:&Recovered)->Recovered {
    first.iter().filter(|(y,name,price)|second.iter().any(|(other_y,other_name,other_price)|
        y.abs_diff(*other_y)<=2 && name==other_name && price==other_price)).cloned().collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn accepts_only_same_name_quantity_and_full_price_in_both_reads() {
        let row=(10,"Example sword".into(),ListedPrice{quantity:1,mesos:149_999});
        assert_eq!(consensus(&vec![row.clone()],&vec![(11,row.1.clone(),row.2)]),vec![row.clone()]);
        for other in [(10,"Other sword".into(),row.2),
                      (10,row.1.clone(),ListedPrice{quantity:1,mesos:14_999}),
                      (10,row.1.clone(),ListedPrice{quantity:2,mesos:149_999}),
                      (30,row.1.clone(),row.2)] {
            assert!(consensus(&vec![row.clone()],&vec![other]).is_empty());
        }
    }
}
