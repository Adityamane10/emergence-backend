from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import httpx
from pymongo import MongoClient
from datetime import datetime

load_dotenv()

app = FastAPI()

cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:5173")
origins = [origin.strip() for origin in cors_origins_str.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017/"))
db = client.portfolio_db
chats_collection = db.chats
resume_collection = db.resume

def initialize_resume():
    if resume_collection.count_documents({}) == 0:
        resume_data = {
            "personal_info": {
                "name": "Aditya Avinash Mane",
                "title": "Full Stack Developer & MCA Student",
                "email": "adityamane4650@gmail.com",
                "mobile": "+91 9673594650",
                "location": "India"
            },
            "education": [
                {
                    "degree": "Master of Computer Applications (MCA)",
                    "status": "Currently in Final Year (2nd Year)",
                    "institution": "University Name"
                },
                {
                    "degree": "Bachelor of Computer Applications (BCA)",
                    "status": "Completed",
                    "institution": "University Name"
                }
            ],
            "skills": {
                "Frontend": ["React", "Next.js", "TypeScript", "JavaScript", "HTML", "CSS", "Tailwind CSS"],
                "Backend": ["Python", "FastAPI", "Node.js", "Nest.js", "Express"],
                "Database": ["MongoDB", "PostgreSQL", "MySQL"],
                "AI/ML": ["OpenAI", "OpenRouter API Integration"],
                "Tools": ["Git", "Docker", "VS Code"],
                "Other": ["REST APIs", "Responsive Design", "Full Stack Development"]
            },
            "projects": [
                {
                    "name": "AI-Powered Portfolio",
                    "description": "Interactive portfolio website with AI chat functionality using React, TypeScript, Python FastAPI, MongoDB, and OpenRouter API",
                    "technologies": ["React", "TypeScript", "Python", "FastAPI", "MongoDB", "OpenRouter"]
                },
                {
                    "name": "Full Stack Web Applications",
                    "description": "Built various web applications using modern tech stack",
                    "technologies": ["React", "Node.js", "Express", "MongoDB"]
                }
            ],
            "about": "Aditya is a passionate Full Stack Developer currently pursuing his Master's in Computer Applications. With a strong foundation in both frontend and backend technologies, he specializes in building modern, responsive web applications. He has hands-on experience with AI integration, database management, and creating seamless user experiences."
        }
        resume_collection.insert_one(resume_data)

initialize_resume()

def get_resume_context():
    resume = resume_collection.find_one()
    if not resume:
        return "No resume data available."
    
    personal = resume.get("personal_info", {})
    education = resume.get("education", [])
    skills = resume.get("skills", {})
    projects = resume.get("projects", [])
    about = resume.get("about", "")
    
    context = f"""
You are an AI assistant for {personal.get('name', 'the candidate')}'s portfolio website. Answer questions about their background, skills, and experience professionally and concisely.

Name: {personal.get('name')}
Title: {personal.get('title')}
Email: {personal.get('email')}
Mobile: {personal.get('mobile')}
Location: {personal.get('location', 'Not specified')}

Education:
"""
    for edu in education:
        context += f"- {edu.get('degree')} - {edu.get('status')}\n"
    
    context += "\nSkills:\n"
    for category, skill_list in skills.items():
        context += f"- {category}: {', '.join(skill_list)}\n"
    
    context += "\nProjects:\n"
    for proj in projects:
        context += f"- {proj.get('name')}: {proj.get('description')}\n"
    
    context += f"\nAbout:\n{about}\n"
    context += "\nAnswer questions naturally and professionally. If asked about something not mentioned here, politely indicate that information is not available."
    
    return context

class ChatMessage(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    timestamp: str

@app.get("/")
def read_root():
    return {"status": "Portfolio API is running"}

@app.post("/api/chat", response_model=ChatResponse)
async def chat(chat_message: ChatMessage):
    try:
        api_key = os.getenv('OPENROUTER_API_KEY')
        if not api_key or api_key == 'your_openrouter_api_key_here':
            raise HTTPException(
                status_code=500, 
                detail="OpenRouter API key not configured. Please add your API key to backend/.env file. Get a free key at https://openrouter.ai/"
            )
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "openrouter/auto:free",
                    "messages": [
                        {"role": "system", "content": get_resume_context()},
                        {"role": "user", "content": chat_message.message}
                    ]
                },
                timeout=30.0
            )
            
            if response.status_code != 200:
                error_detail = response.json() if response.text else "AI service error"
                raise HTTPException(status_code=500, detail=f"AI service error: {error_detail}")
            
            ai_response = response.json()["choices"][0]["message"]["content"]
        
        try:
            timestamp = datetime.utcnow().isoformat()
            chats_collection.insert_one({
                "user_message": chat_message.message,
                "ai_response": ai_response,
                "timestamp": timestamp
            })
        except Exception as db_error:
            timestamp = datetime.utcnow().isoformat()
        
        return ChatResponse(response=ai_response, timestamp=timestamp)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chat/history")
async def get_chat_history(limit: int = 10):
    try:
        chats = list(chats_collection.find().sort("timestamp", -1).limit(limit))
        for chat in chats:
            chat["_id"] = str(chat["_id"])
        return {"chats": chats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/resume")
async def get_resume():
    try:
        resume = resume_collection.find_one()
        if resume:
            resume["_id"] = str(resume["_id"])
        return resume or {"message": "No resume data found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/resume")
async def update_resume(resume_data: dict):
    try:
        result = resume_collection.replace_one({}, resume_data, upsert=True)
        return {"message": "Resume updated successfully", "modified": result.modified_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
