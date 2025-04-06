# IFAD Multimodal RAG Assistant

This project is a **Multimodal Retrieval-Augmented Generation (RAG)** assistant built to help navigate and analyze 240 long-form IFAD (International Fund for Agricultural Development) project reports.

It supports **text + image retrieval**, generates contextual answers with citations, and is deployable as a production-ready backend.

---

## 🌐 Live Demo
https://v0-mrag-interface.vercel.app/
*(If it doesn’t respond at first, try again — Cloud Run may be cold-starting.)*

---

## 🔧 Tech Stack

- **Language Model**: Google Gemini 2.0 Flash
- **Vector Search**: FAISS
- **Embedding Models**:
  - Text: `text-embedding-005`
  - Image: Gemini’s multimodal embeddings (via `mm_embedding_from_img_only`)
- **Backend**: FastAPI
- **Deployment**: Cloud Run (via Docker)
- **Preprocessing**: Vertex AI Workbench (Python notebooks)

---

## 📦 Dataset
- **240 IFAD PDF reports**
- ~**90,000 text chunks** (7-column Parquet file)
- ~**3,000 images** (cleaned, deduplicated, logo-filtered)

Text Columns:
```
file_name, page_num, text, text_embedding_page, chunk_number, chunk_text, text_embedding_chunk
```

Image Columns:
```
file_name, page_num, img_num, img_path, img_desc, mm_embedding_from_img_only, text_embedding_from_image_description
```

---

## 🚀 Features
- ✅ Natural language Q&A with Gemini
- ✅ Text + image retrieval from IFAD reports
- ✅ Returns relevant text chunks and image captions
- ✅ Base64 encoded image display in frontend
- ✅ Cloud Run optimized (memory-efficient)
- ✅ Full FAISS index loading on startup (text + image)

---

## ⚠️ Known Limitations
- ❌ Some image paths fail to load in production, despite working locally
- ❌ Identical images can appear twice if captions differ
- ❌ Scanned tables are currently stored as images; no structured extraction yet

Planned:
- [ ] Handle scanned tables more intelligently (possibly via OCR + table detection)
- [ ] Add quote-based follow-up support
- [ ] Push code to GitHub with deployment scripts
- [ ] Image reasoning improvements

---

## 📜 Legal / Disclaimer
This project is non-commercial and built for demo purposes only.

The IFAD PDF reports are publicly accessible via: https://www.ifad.org/

If required, I can add a disclaimer link on the frontend.

---

## 👤 About Me
I built this over 24 days (March 7–31, 2025), originally intending to complete it in one week — but perfectionism and ambition led to many late nights debugging embedding mismatches, vector loading, Cloud Run cold starts, and image rendering issues.

This is the assistant I wish I had while analyzing the Ukraine war’s impact on NEN countries at IFAD. 

Built with love and frustration.

---

## 🧠 Contact
Want to collaborate or learn more?
Find me on [LinkedIn](https://www.linkedin.com/in/ywwanda/) or reach out at `ucsdwanda@gmail.com`.

