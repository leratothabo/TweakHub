"""
Data-driven tool registry.

TweakHub's pitch is "200+ tools" — the way to actually reach and maintain
that number without 200 hand-written route handlers is to keep the catalog
as data and let ToolRouter dispatch generically off it. This file seeds the
catalog with representative tools across the five categories the plan
calls out (PDF, image, video, audio, document). Reaching the full 200 is a
matter of appending more entries in the same shape — not writing more code.

The "specific named pair" tools below (png_to_jpg, mp4_to_webm, docx_to_txt,
and similar) are deliberately not just aliases of the generic
image_convert/video_convert/audio_convert tools that already cover any
target_format — that's the actual shape of this market (people search "png
to jpg converter", not "image format converter"), and it's how the batch
in this pass was built: each one reuses an already-verified handler
(_image_convert/_video_convert/_audio_convert/_libreoffice_convert) with a
fixed engine_op, not new engine code, and every new pair was independently
confirmed working against a real generated file before being added here —
see the corresponding tests in apps/api/tests/test_engines.py, not just
"the generic version already works so this probably does too."

Each entry:
  name          - stable slug used in URLs and credit-cost lookups
  label         - human-readable name shown in the UI
  category      - pdf | image | video | audio | document
  engine        - which engine key in ToolRouter.engines handles it
  base_credits  - baseline credit cost (see credit_service.get_credit_cost)
  engine_op     - operation/format hint passed through to the engine
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    label: str
    category: str
    engine: str
    base_credits: int
    engine_op: str


TOOLS: list[ToolSpec] = [
    # --- PDF: manipulate (php-pdf) ---
    ToolSpec("pdf_merge", "Merge PDF", "pdf", "manipulate", 5, "merge"),
    ToolSpec("pdf_split", "Split PDF", "pdf", "manipulate", 3, "split"),
    ToolSpec("pdf_extract_pages", "Extract Pages", "pdf", "manipulate", 3, "extract_pages"),
    ToolSpec("pdf_watermark", "Add Watermark", "pdf", "manipulate", 4, "watermark"),
    ToolSpec("pdf_rotate", "Rotate Pages", "pdf", "manipulate", 2, "rotate"),
    ToolSpec("pdf_crop", "Crop PDF", "pdf", "manipulate", 3, "crop"),
    ToolSpec("pdf_add_page_numbers", "Add Page Numbers", "pdf", "manipulate", 2, "page_numbers"),
    ToolSpec("pdf_protect", "Password Protect PDF", "pdf", "manipulate", 4, "protect"),
    ToolSpec("pdf_unlock", "Remove PDF Password", "pdf", "manipulate", 4, "unlock"),
    ToolSpec("pdf_sign", "Sign PDF", "pdf", "manipulate", 6, "sign"),
    ToolSpec("pdf_redact", "Redact PDF", "pdf", "manipulate", 6, "redact"),
    ToolSpec("pdf_repair", "Repair PDF", "pdf", "manipulate", 5, "repair"),
    ToolSpec("pdf_compress", "Compress PDF", "pdf", "manipulate", 8, "compress"),
    ToolSpec("pdf_organize", "Organize / Reorder Pages", "pdf", "manipulate", 3, "organize"),
    ToolSpec("pdf_to_pdfa", "Convert to PDF/A", "pdf", "manipulate", 6, "pdfa"),
    # --- PDF: edit (PDFEditor, client-side + server flatten) ---
    ToolSpec("pdf_edit", "Edit PDF", "pdf", "edit", 6, "flatten"),
    ToolSpec("pdf_annotate", "Annotate PDF", "pdf", "edit", 4, "flatten"),
    ToolSpec("pdf_fill_form", "Fill PDF Form", "pdf", "edit", 4, "flatten"),
    # --- PDF <-> document (ConvertAgent) ---
    ToolSpec("pdf_to_word", "PDF to Word", "document", "document", 15, "pdf_to_docx"),
    ToolSpec("word_to_pdf", "Word to PDF", "document", "document", 10, "docx_to_pdf"),
    ToolSpec("html_to_pdf", "HTML to PDF", "document", "document", 8, "html_to_pdf"),
    ToolSpec("pdf_to_html", "PDF to HTML", "document", "document", 10, "pdf_to_html"),
    ToolSpec("markdown_to_pdf", "Markdown to PDF", "document", "document", 6, "markdown_to_pdf"),
    ToolSpec("pdf_to_markdown", "PDF to Markdown", "document", "document", 10, "pdf_to_markdown"),
    ToolSpec("ocr_extract", "OCR: Scanned PDF to Searchable", "pdf", "document", 20, "ocr_pdf"),
    # --- PDF: generate (TerraPDF) ---
    ToolSpec("invoice_generator", "Generate Invoice PDF", "pdf", "generate", 5, "invoice"),
    ToolSpec("certificate_generator", "Generate Certificate PDF", "pdf", "generate", 5, "certificate"),
    ToolSpec("report_generator", "Generate Report PDF", "pdf", "generate", 8, "report"),
    # --- PDF <-> other formats (AVX) ---
    ToolSpec("pdf_to_jpg", "PDF to JPG", "pdf", "convert", 5, "target_format=jpg"),
    ToolSpec("jpg_to_pdf", "JPG to PDF", "pdf", "convert", 5, "target_format=pdf"),
    ToolSpec("png_to_pdf", "PNG to PDF", "pdf", "convert", 5, "target_format=pdf"),
    ToolSpec("webp_to_pdf", "WebP to PDF", "pdf", "convert", 5, "target_format=pdf"),
    ToolSpec("gif_to_pdf", "GIF to PDF", "pdf", "convert", 5, "target_format=pdf"),
    ToolSpec("bmp_to_pdf", "BMP to PDF", "pdf", "convert", 5, "target_format=pdf"),
    ToolSpec("tiff_to_pdf", "TIFF to PDF", "pdf", "convert", 5, "target_format=pdf"),
    ToolSpec("pdf_to_png", "PDF to PNG", "pdf", "convert", 5, "target_format=png"),
    # pdftoppm (poppler) natively supports a third output format beyond
    # jpg/png — verified with `pdftoppm -h` before relying on it, same
    # _pdf_to_image handler, one more entry in its format->flag mapping.
    ToolSpec("pdf_to_tiff", "PDF to TIFF", "pdf", "convert", 5, "target_format=tiff"),
    ToolSpec("pdf_to_excel", "PDF to Excel", "document", "document", 15, "pdf_to_xlsx"),
    ToolSpec("excel_to_pdf", "Excel to PDF", "document", "document", 10, "xlsx_to_pdf"),
    ToolSpec("pdf_to_ppt", "PDF to PowerPoint", "document", "document", 15, "pdf_to_pptx"),
    ToolSpec("ppt_to_pdf", "PowerPoint to PDF", "document", "document", 10, "pptx_to_pdf"),
    ToolSpec("pdf_to_text", "PDF to Text", "pdf", "convert", 3, "target_format=txt"),
    ToolSpec("text_to_pdf", "Text to PDF", "pdf", "convert", 3, "target_format=pdf"),
    ToolSpec("pdf_compare", "Compare Two PDFs", "pdf", "convert", 6, "compare"),
    # --- Image (AVX) ---
    ToolSpec("image_convert", "Convert Image Format", "image", "convert", 5, "target_format"),
    ToolSpec("image_resize", "Resize Image", "image", "convert", 3, "resize"),
    ToolSpec("image_compress", "Compress Image", "image", "convert", 4, "compress"),
    ToolSpec("image_crop", "Crop Image", "image", "convert", 2, "crop"),
    ToolSpec("image_to_pdf", "Image(s) to PDF", "image", "convert", 5, "target_format=pdf"),
    ToolSpec("image_bg_remove", "Remove Background", "image", "convert", 12, "bg_remove"),
    ToolSpec("image_watermark", "Watermark Image", "image", "convert", 3, "watermark"),
    ToolSpec("image_rotate", "Rotate Image", "image", "convert", 2, "rotate"),
    ToolSpec("heic_to_jpg", "HEIC to JPG", "image", "convert", 4, "target_format=jpg"),
    ToolSpec("svg_to_png", "SVG to PNG", "image", "convert", 3, "target_format=png"),
    ToolSpec("webp_convert", "WebP Converter", "image", "convert", 3, "target_format"),
    # --- Image: specific named format pairs (reuse _image_convert — see
    # tools_catalog.py's module docstring for why these aren't just
    # aliases of image_convert) ---
    ToolSpec("png_to_jpg", "PNG to JPG", "image", "convert", 3, "target_format=jpg"),
    ToolSpec("jpg_to_png", "JPG to PNG", "image", "convert", 3, "target_format=png"),
    ToolSpec("png_to_webp", "PNG to WebP", "image", "convert", 3, "target_format=webp"),
    ToolSpec("webp_to_png", "WebP to PNG", "image", "convert", 3, "target_format=png"),
    ToolSpec("bmp_to_png", "BMP to PNG", "image", "convert", 3, "target_format=png"),
    ToolSpec("png_to_bmp", "PNG to BMP", "image", "convert", 3, "target_format=bmp"),
    ToolSpec("tiff_to_png", "TIFF to PNG", "image", "convert", 3, "target_format=png"),
    ToolSpec("png_to_tiff", "PNG to TIFF", "image", "convert", 3, "target_format=tiff"),
    ToolSpec("gif_to_png", "GIF to PNG", "image", "convert", 3, "target_format=png"),
    # --- Image: remaining named pairs among the same six formats above
    # (jpg/png/webp/gif/bmp/tiff — all already in IMAGE_FORMAT_MIME), same
    # _image_convert handler, filling out the ordered-pair grid rather than
    # leaving asymmetric coverage (e.g. png_to_gif existed with no
    # jpg_to_gif) — each pair independently confirmed against a real
    # generated image before being added, see test_engines.py ---
    ToolSpec("jpg_to_webp", "JPG to WebP", "image", "convert", 3, "target_format=webp"),
    ToolSpec("jpg_to_gif", "JPG to GIF", "image", "convert", 3, "target_format=gif"),
    ToolSpec("jpg_to_bmp", "JPG to BMP", "image", "convert", 3, "target_format=bmp"),
    ToolSpec("jpg_to_tiff", "JPG to TIFF", "image", "convert", 3, "target_format=tiff"),
    ToolSpec("png_to_gif", "PNG to GIF", "image", "convert", 3, "target_format=gif"),
    ToolSpec("webp_to_jpg", "WebP to JPG", "image", "convert", 3, "target_format=jpg"),
    ToolSpec("webp_to_gif", "WebP to GIF", "image", "convert", 3, "target_format=gif"),
    ToolSpec("webp_to_bmp", "WebP to BMP", "image", "convert", 3, "target_format=bmp"),
    ToolSpec("webp_to_tiff", "WebP to TIFF", "image", "convert", 3, "target_format=tiff"),
    ToolSpec("gif_to_jpg", "GIF to JPG", "image", "convert", 3, "target_format=jpg"),
    ToolSpec("gif_to_webp", "GIF to WebP", "image", "convert", 3, "target_format=webp"),
    ToolSpec("gif_to_bmp", "GIF to BMP", "image", "convert", 3, "target_format=bmp"),
    ToolSpec("gif_to_tiff", "GIF to TIFF", "image", "convert", 3, "target_format=tiff"),
    ToolSpec("bmp_to_jpg", "BMP to JPG", "image", "convert", 3, "target_format=jpg"),
    ToolSpec("bmp_to_webp", "BMP to WebP", "image", "convert", 3, "target_format=webp"),
    ToolSpec("bmp_to_gif", "BMP to GIF", "image", "convert", 3, "target_format=gif"),
    ToolSpec("bmp_to_tiff", "BMP to TIFF", "image", "convert", 3, "target_format=tiff"),
    ToolSpec("tiff_to_jpg", "TIFF to JPG", "image", "convert", 3, "target_format=jpg"),
    ToolSpec("tiff_to_webp", "TIFF to WebP", "image", "convert", 3, "target_format=webp"),
    ToolSpec("tiff_to_gif", "TIFF to GIF", "image", "convert", 3, "target_format=gif"),
    ToolSpec("tiff_to_bmp", "TIFF to BMP", "image", "convert", 3, "target_format=bmp"),
    # --- Image: new formats this pass — ICO (favicons) and AVIF (modern
    # web images), both confirmed working in this Pillow build with no
    # new dependency, same _image_convert handler ---
    ToolSpec("png_to_ico", "PNG to ICO (Favicon)", "image", "convert", 3, "target_format=ico"),
    ToolSpec("ico_to_png", "ICO to PNG", "image", "convert", 3, "target_format=png"),
    ToolSpec("jpg_to_ico", "JPG to ICO (Favicon)", "image", "convert", 3, "target_format=ico"),
    ToolSpec("png_to_avif", "PNG to AVIF", "image", "convert", 4, "target_format=avif"),
    ToolSpec("avif_to_png", "AVIF to PNG", "image", "convert", 4, "target_format=png"),
    ToolSpec("jpg_to_avif", "JPG to AVIF", "image", "convert", 4, "target_format=avif"),
    ToolSpec("avif_to_jpg", "AVIF to JPG", "image", "convert", 4, "target_format=jpg"),
    ToolSpec("webp_to_avif", "WebP to AVIF", "image", "convert", 4, "target_format=avif"),
    ToolSpec("avif_to_webp", "AVIF to WebP", "image", "convert", 4, "target_format=webp"),
    # --- Video (AVX) ---
    ToolSpec("video_compress", "Compress Video", "video", "convert", 30, "compress"),
    ToolSpec("video_convert", "Convert Video Format", "video", "convert", 20, "target_format"),
    ToolSpec("video_trim", "Trim / Cut Video", "video", "convert", 15, "trim"),
    ToolSpec("video_to_gif", "Video to GIF", "video", "convert", 15, "target_format=gif"),
    ToolSpec("video_extract_audio", "Extract Audio from Video", "video", "convert", 10, "extract_audio"),
    ToolSpec("video_merge", "Merge Videos", "video", "convert", 25, "merge"),
    ToolSpec("video_resize", "Resize / Change Resolution", "video", "convert", 20, "resize"),
    ToolSpec("video_watermark", "Watermark Video", "video", "convert", 20, "watermark"),
    ToolSpec("video_mute", "Remove Audio from Video", "video", "convert", 10, "mute"),
    ToolSpec("subtitle_burn", "Burn Subtitles into Video", "video", "convert", 20, "burn_subtitles"),
    # --- Video: specific named format pairs (reuse _video_convert; ffmpeg
    # sniffs real container/codec content regardless of the scratch file's
    # extension, verified against each of these pairs specifically — see
    # test_engines.py) ---
    ToolSpec("mp4_to_webm", "MP4 to WebM", "video", "convert", 18, "target_format=webm"),
    ToolSpec("webm_to_mp4", "WebM to MP4", "video", "convert", 18, "target_format=mp4"),
    ToolSpec("mp4_to_mkv", "MP4 to MKV", "video", "convert", 15, "target_format=mkv"),
    ToolSpec("mkv_to_mp4", "MKV to MP4", "video", "convert", 15, "target_format=mp4"),
    ToolSpec("mp4_to_mov", "MP4 to MOV", "video", "convert", 15, "target_format=mov"),
    ToolSpec("mov_to_mp4", "MOV to MP4", "video", "convert", 15, "target_format=mp4"),
    # --- Video: remaining pairs among mp4/webm/mkv/mov, plus two more
    # widely-searched containers (avi, flv) bidirectional with mp4 — same
    # _video_convert handler and same ffmpeg-content-sniffing reasoning as
    # the six pairs above, each confirmed against a real generated clip ---
    ToolSpec("webm_to_mkv", "WebM to MKV", "video", "convert", 15, "target_format=mkv"),
    ToolSpec("mkv_to_webm", "MKV to WebM", "video", "convert", 18, "target_format=webm"),
    ToolSpec("webm_to_mov", "WebM to MOV", "video", "convert", 15, "target_format=mov"),
    ToolSpec("mov_to_webm", "MOV to WebM", "video", "convert", 18, "target_format=webm"),
    ToolSpec("mkv_to_mov", "MKV to MOV", "video", "convert", 15, "target_format=mov"),
    ToolSpec("mov_to_mkv", "MOV to MKV", "video", "convert", 15, "target_format=mkv"),
    ToolSpec("mp4_to_avi", "MP4 to AVI", "video", "convert", 15, "target_format=avi"),
    ToolSpec("avi_to_mp4", "AVI to MP4", "video", "convert", 15, "target_format=mp4"),
    ToolSpec("mp4_to_flv", "MP4 to FLV", "video", "convert", 15, "target_format=flv"),
    ToolSpec("flv_to_mp4", "FLV to MP4", "video", "convert", 15, "target_format=mp4"),
    # --- Video: new containers this pass, bidirectional with mp4 — same
    # _video_convert handler ---
    ToolSpec("mp4_to_wmv", "MP4 to WMV", "video", "convert", 15, "target_format=wmv"),
    ToolSpec("wmv_to_mp4", "WMV to MP4", "video", "convert", 15, "target_format=mp4"),
    ToolSpec("mp4_to_ts", "MP4 to TS", "video", "convert", 15, "target_format=ts"),
    ToolSpec("ts_to_mp4", "TS to MP4", "video", "convert", 15, "target_format=mp4"),
    ToolSpec("mp4_to_m4v", "MP4 to M4V", "video", "convert", 15, "target_format=m4v"),
    ToolSpec("m4v_to_mp4", "M4V to MP4", "video", "convert", 15, "target_format=mp4"),
    # --- Video: named "video to mp3" extraction pairs — reuse
    # _video_extract_audio (already-verified generic handler, source
    # container doesn't matter — same content-sniffing behavior as
    # _video_convert). Huge real-world search volume this catalog was
    # missing named entries for. ---
    ToolSpec("mp4_to_mp3", "MP4 to MP3", "video", "convert", 10, "extract_audio"),
    ToolSpec("mov_to_mp3", "MOV to MP3", "video", "convert", 10, "extract_audio"),
    ToolSpec("webm_to_mp3", "WebM to MP3", "video", "convert", 10, "extract_audio"),
    ToolSpec("mkv_to_mp3", "MKV to MP3", "video", "convert", 10, "extract_audio"),
    ToolSpec("avi_to_mp3", "AVI to MP3", "video", "convert", 10, "extract_audio"),
    # Remaining containers — completes "extract audio to mp3" for every
    # video format this catalog supports, same handler.
    ToolSpec("flv_to_mp3", "FLV to MP3", "video", "convert", 10, "extract_audio"),
    ToolSpec("wmv_to_mp3", "WMV to MP3", "video", "convert", 10, "extract_audio"),
    ToolSpec("ts_to_mp3", "TS to MP3", "video", "convert", 10, "extract_audio"),
    ToolSpec("m4v_to_mp3", "M4V to MP3", "video", "convert", 10, "extract_audio"),
    # --- Audio (AVX) ---
    ToolSpec("audio_convert", "Convert Audio Format", "audio", "convert", 5, "target_format"),
    ToolSpec("audio_compress", "Compress Audio", "audio", "convert", 5, "compress"),
    ToolSpec("audio_trim", "Trim Audio", "audio", "convert", 4, "trim"),
    ToolSpec("audio_merge", "Merge Audio Files", "audio", "convert", 6, "merge"),
    ToolSpec("audio_normalize", "Normalize Audio Volume", "audio", "convert", 5, "normalize"),
    ToolSpec("audio_to_text", "Transcribe Audio to Text", "audio", "convert", 25, "transcribe"),
    # --- Audio: specific named format pairs (reuse _audio_convert) ---
    ToolSpec("mp3_to_wav", "MP3 to WAV", "audio", "convert", 4, "target_format=wav"),
    ToolSpec("wav_to_mp3", "WAV to MP3", "audio", "convert", 4, "target_format=mp3"),
    ToolSpec("wav_to_flac", "WAV to FLAC", "audio", "convert", 4, "target_format=flac"),
    ToolSpec("flac_to_mp3", "FLAC to MP3", "audio", "convert", 4, "target_format=mp3"),
    ToolSpec("wav_to_ogg", "WAV to OGG", "audio", "convert", 4, "target_format=ogg"),
    ToolSpec("ogg_to_mp3", "OGG to MP3", "audio", "convert", 4, "target_format=mp3"),
    ToolSpec("wav_to_m4a", "WAV to M4A (AAC)", "audio", "convert", 4, "target_format=m4a"),
    ToolSpec("m4a_to_mp3", "M4A to MP3", "audio", "convert", 4, "target_format=mp3"),
    # --- Audio: remaining named pairs among mp3/wav/flac/ogg/m4a, same
    # _audio_convert handler, filling out the ordered-pair grid (each pair
    # independently confirmed against a real generated tone, see
    # test_engines.py) ---
    ToolSpec("mp3_to_flac", "MP3 to FLAC", "audio", "convert", 4, "target_format=flac"),
    ToolSpec("flac_to_wav", "FLAC to WAV", "audio", "convert", 4, "target_format=wav"),
    ToolSpec("mp3_to_ogg", "MP3 to OGG", "audio", "convert", 4, "target_format=ogg"),
    ToolSpec("ogg_to_wav", "OGG to WAV", "audio", "convert", 4, "target_format=wav"),
    ToolSpec("mp3_to_m4a", "MP3 to M4A", "audio", "convert", 4, "target_format=m4a"),
    ToolSpec("m4a_to_wav", "M4A to WAV", "audio", "convert", 4, "target_format=wav"),
    ToolSpec("flac_to_ogg", "FLAC to OGG", "audio", "convert", 4, "target_format=ogg"),
    ToolSpec("ogg_to_flac", "OGG to FLAC", "audio", "convert", 4, "target_format=flac"),
    ToolSpec("flac_to_m4a", "FLAC to M4A", "audio", "convert", 4, "target_format=m4a"),
    ToolSpec("m4a_to_flac", "M4A to FLAC", "audio", "convert", 4, "target_format=flac"),
    ToolSpec("ogg_to_m4a", "OGG to M4A", "audio", "convert", 4, "target_format=m4a"),
    ToolSpec("m4a_to_ogg", "M4A to OGG", "audio", "convert", 4, "target_format=ogg"),
    # --- Audio: new formats this pass — same _audio_convert handler ---
    ToolSpec("mp3_to_opus", "MP3 to Opus", "audio", "convert", 4, "target_format=opus"),
    ToolSpec("opus_to_mp3", "Opus to MP3", "audio", "convert", 4, "target_format=mp3"),
    ToolSpec("mp3_to_aac", "MP3 to AAC", "audio", "convert", 4, "target_format=aac"),
    ToolSpec("aac_to_mp3", "AAC to MP3", "audio", "convert", 4, "target_format=mp3"),
    ToolSpec("mp3_to_wma", "MP3 to WMA", "audio", "convert", 4, "target_format=wma"),
    ToolSpec("wma_to_mp3", "WMA to MP3", "audio", "convert", 4, "target_format=mp3"),
    ToolSpec("mp3_to_aiff", "MP3 to AIFF", "audio", "convert", 4, "target_format=aiff"),
    ToolSpec("aiff_to_mp3", "AIFF to MP3", "audio", "convert", 4, "target_format=mp3"),
    # --- Audio: connect opus/aac/wma/aiff to the wav hub too, not just
    # mp3 (flac/ogg/m4a already had both) — same _audio_convert handler ---
    ToolSpec("wav_to_opus", "WAV to Opus", "audio", "convert", 4, "target_format=opus"),
    ToolSpec("opus_to_wav", "Opus to WAV", "audio", "convert", 4, "target_format=wav"),
    ToolSpec("wav_to_aac", "WAV to AAC", "audio", "convert", 4, "target_format=aac"),
    ToolSpec("aac_to_wav", "AAC to WAV", "audio", "convert", 4, "target_format=wav"),
    ToolSpec("wav_to_wma", "WAV to WMA", "audio", "convert", 4, "target_format=wma"),
    ToolSpec("wma_to_wav", "WMA to WAV", "audio", "convert", 4, "target_format=wav"),
    ToolSpec("wav_to_aiff", "WAV to AIFF", "audio", "convert", 4, "target_format=aiff"),
    ToolSpec("aiff_to_wav", "AIFF to WAV", "audio", "convert", 4, "target_format=wav"),
    # --- Document (AVX / ConvertAgent) ---
    ToolSpec("csv_to_xlsx", "CSV to Excel", "document", "convert", 4, "target_format=xlsx"),
    ToolSpec("xlsx_to_csv", "Excel to CSV", "document", "convert", 4, "target_format=csv"),
    ToolSpec("odt_to_pdf", "ODT to PDF", "document", "document", 8, "odt_to_pdf"),
    ToolSpec("docx_to_odt", "DOCX to ODT", "document", "document", 8, "docx_to_odt"),
    ToolSpec("epub_to_pdf", "EPUB to PDF", "document", "document", 10, "epub_to_pdf"),
    ToolSpec("rtf_to_pdf", "RTF to PDF", "document", "document", 6, "rtf_to_pdf"),
    # --- Document: additional real LibreOffice pairs (reuse
    # _libreoffice_convert via _LIBREOFFICE_JOBS in document_convert.py —
    # each verified against a real generated seed file, same discipline
    # as the pdf_to_excel/pdf_to_ppt/epub_to_pdf stubs that were tried and
    # found NOT to work; these four were tried and do work) ---
    ToolSpec("docx_to_txt", "Word to Plain Text", "document", "document", 5, "docx_to_txt"),
    ToolSpec("odt_to_docx", "ODT to Word", "document", "document", 8, "odt_to_docx"),
    ToolSpec("xlsx_to_ods", "Excel to ODS", "document", "document", 6, "xlsx_to_ods"),
    ToolSpec("ods_to_xlsx", "ODS to Excel", "document", "document", 6, "ods_to_xlsx"),
    # --- Document: presentation/text pairs added to _LIBREOFFICE_JOBS in
    # document_convert.py (same generic _libreoffice_convert handler,
    # data-only additions) — each verified against a real generated seed
    # file before being added here, see test_engines.py ---
    ToolSpec("pptx_to_odp", "PowerPoint to ODP", "document", "document", 8, "pptx_to_odp"),
    ToolSpec("odp_to_pptx", "ODP to PowerPoint", "document", "document", 8, "odp_to_pptx"),
    ToolSpec("odp_to_pdf", "ODP to PDF", "document", "document", 8, "odp_to_pdf"),
    ToolSpec("txt_to_docx", "Text to Word", "document", "document", 5, "txt_to_docx"),
    # --- Document: new LibreOffice pairs this pass — same generic
    # _libreoffice_convert handler, new _LIBREOFFICE_JOBS entries ---
    ToolSpec("html_to_docx", "HTML to Word", "document", "document", 6, "html_to_docx"),
    ToolSpec("docx_to_html", "Word to HTML", "document", "document", 6, "docx_to_html"),
    ToolSpec("odt_to_txt", "ODT to Plain Text", "document", "document", 5, "odt_to_txt"),
    ToolSpec("rtf_to_docx", "RTF to Word", "document", "document", 6, "rtf_to_docx"),
    # --- Document: legacy Word 97-2003 (.doc) / Excel 97-2003 (.xls) and
    # CSV — new _LIBREOFFICE_JOBS entries, same generic
    # _libreoffice_convert handler. Each verified round-tripped through
    # actual preserved content, not just "produced a file" — see
    # document_convert.py's _LIBREOFFICE_JOBS comment. ---
    ToolSpec("doc_to_pdf", "DOC to PDF", "document", "document", 8, "doc_to_pdf"),
    ToolSpec("doc_to_docx", "DOC to Word (DOCX)", "document", "document", 6, "doc_to_docx"),
    ToolSpec("xls_to_xlsx", "XLS to Excel (XLSX)", "document", "document", 6, "xls_to_xlsx"),
    ToolSpec("xls_to_pdf", "XLS to PDF", "document", "document", 8, "xls_to_pdf"),
    ToolSpec("csv_to_pdf", "CSV to PDF", "document", "document", 6, "csv_to_pdf"),
    # --- Document: closing the remaining natural gaps this pass — ODF
    # spreadsheet to pdf, rtf's missing text/ODF-text pairs, legacy .doc
    # to plain text, legacy .xls to csv — same generic
    # _libreoffice_convert handler, new _LIBREOFFICE_JOBS entries ---
    ToolSpec("ods_to_pdf", "ODS to PDF", "document", "document", 8, "ods_to_pdf"),
    ToolSpec("rtf_to_txt", "RTF to Plain Text", "document", "document", 5, "rtf_to_txt"),
    ToolSpec("rtf_to_odt", "RTF to ODT", "document", "document", 6, "rtf_to_odt"),
    ToolSpec("doc_to_txt", "DOC to Plain Text", "document", "document", 5, "doc_to_txt"),
    ToolSpec("xls_to_csv", "XLS to CSV", "document", "document", 5, "xls_to_csv"),
    # --- Document: ODF spreadsheet <-> CSV — same CSV export filter
    # already verified for xls_to_csv (re-verified here against a real
    # ODS this time) plus the reverse import direction, same generic
    # _libreoffice_convert handler, two new _LIBREOFFICE_JOBS entries. ---
    ToolSpec("ods_to_csv", "ODS to CSV", "document", "document", 5, "ods_to_csv"),
    ToolSpec("csv_to_ods", "CSV to ODS", "document", "document", 6, "csv_to_ods"),
]

TOOLS_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in TOOLS}


def list_tools(category: str | None = None) -> list[ToolSpec]:
    if category:
        return [t for t in TOOLS if t.category == category]
    return list(TOOLS)


def get_tool(name: str) -> ToolSpec | None:
    return TOOLS_BY_NAME.get(name)
