//! Narrow, demand-only OCR using the same bundled recognition weights as Minerva.
use image::{GrayImage, Luma};
use ocrs::{ImageSource, OcrEngine, OcrEngineParams};
use rten::Model;
use rten_imageproc::{RectF, RotatedRect};
use std::sync::OnceLock;

pub fn read(ink: &GrayImage) -> Option<String> {
    read_scaled(ink,2,image::imageops::FilterType::Triangle)
}

pub fn read_scaled(ink:&GrayImage, scale:u32, filter:image::imageops::FilterType)->Option<String> {
    let mut bounds=(ink.width(),ink.height(),0,0);
    for (x,y,p) in ink.enumerate_pixels() {
        if p.0[0]<180 {bounds.0=bounds.0.min(x);bounds.1=bounds.1.min(y);bounds.2=bounds.2.max(x);bounds.3=bounds.3.max(y);}
    }
    if bounds.0>bounds.2 || bounds.1>bounds.3 {return None}
    let cropped=image::imageops::crop_imm(ink,bounds.0,bounds.1,bounds.2-bounds.0+1,bounds.3-bounds.1+1).to_image();
    let ink=&cropped;
    static ENGINE: OnceLock<OcrEngine> = OnceLock::new();
    let engine = ENGINE.get_or_init(|| {
        let bytes = include_bytes!("../../vendor/minerva/crates/minerva-core/models/text-recognition.onnx");
        let model = Model::load(bytes.to_vec()).expect("bundled recognition weights load");
        OcrEngine::new(OcrEngineParams { recognition_model: Some(model), ..Default::default() })
            .expect("recognition engine builds")
    });
    let mut padded = GrayImage::from_pixel(ink.width()+12, ink.height()+12, Luma([255]));
    image::imageops::replace(&mut padded, ink, 6, 6);
    let canvas = image::imageops::resize(&padded, padded.width()*scale, padded.height()*scale,filter);
    let source = ImageSource::from_bytes(canvas.as_raw(), canvas.dimensions()).ok()?;
    let input = engine.prepare_input(source).ok()?;
    let margin=3.0;
    let line = RotatedRect::from_rect(RectF::from_tlhw((6*scale) as f32-margin, (6*scale) as f32-margin,
                 (ink.height()*scale) as f32+2.0*margin, (ink.width()*scale) as f32+2.0*margin));
    let results = engine.recognize_text(&input, &[vec![line]]).ok()?;
    let value = results.first()?.as_ref()?.to_string();
    let value = value.split_whitespace().collect::<Vec<_>>().join(" ");
    (!value.is_empty()).then_some(value)
}
