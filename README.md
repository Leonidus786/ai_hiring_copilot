# AI Hiring Copilot

An AI-powered hiring assistant that matches resumes to job descriptions, identifies skill gaps, generates interview questions, and creates personalized learning roadmaps.

## Features (Building in 60 Days)
- Resume PDF upload + skill extraction
- Job Description parsing
- AI match score (resume vs JD)
- Skill gap analysis
- Auto-generated interview questions
- Personalized learning roadmap

## Tech Stack
- **Backend:** FastAPI + Python
- **AI/LLM:** Groq (Llama 3) + LangChain
- **Vector DB:** Pinecone
- **Frontend:** Next.js
- **Deploy:** Render (backend) + Vercel (frontend)

## Running Locally

```bash
cd backend
python -m venv venv
venv\Scripts\activate       # Windows
pip install -r requirements.txt
cp .env.example .env        # Add your API keys
uvicorn app:app --reload
```

API docs at: http://localhost:8000/docs

## Day-by-Day Progress
- **Day 1:** PDF upload + text extraction API ✅
- **Day 2:** AI skill extraction with Groq (coming)
- **Day 3:** JD parser (coming)
