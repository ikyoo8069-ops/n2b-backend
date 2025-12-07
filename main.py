from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic
import json

app = FastAPI(title="N2B API", version="1.0.0")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ikyoo8069-ops.github.io", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정부지원사업 데이터
GOV_PROGRAMS = [
    {
        "id": 1,
        "name": "2025년 3차 중소벤처기업부 혁신제품 추가등록",
        "category": "기타",
        "agency": "중소벤처기업부",
        "target": "중소기업",
        "period": "2025-11-06 ~ 2025-12-16",
        "support_amount": "혁신제품 인증",
        "keywords": ["혁신제품", "인증", "규격추가"]
    },
    {
        "id": 2,
        "name": "2025년 우수 물류신기술등 지정 시행",
        "category": "기타",
        "agency": "국토교통부",
        "target": "물류기업",
        "period": "2025-11-04 ~ 2026-12-31",
        "support_amount": "신기술 인증",
        "keywords": ["물류", "신기술", "인증"]
    },
    {
        "id": 3,
        "name": "2025년 IP투자연계 지식재산평가 지원사업",
        "category": "기타",
        "agency": "특허청",
        "target": "IP보유기업",
        "period": "2025-03-07 ~ 2025-12-31",
        "support_amount": "평가비용",
        "keywords": ["IP평가", "지식재산", "투자연계"]
    },
    {
        "id": 4,
        "name": "2025년 친환경경영(ESG) 컨설팅 지원사업",
        "category": "기타",
        "agency": "환경부",
        "target": "중소·중견기업",
        "period": "2025-07-31 ~ 2025-12-31",
        "support_amount": "ESG컨설팅",
        "keywords": ["ESG", "친환경", "컨설팅", "탄소중립"]
    },
    {
        "id": 5,
        "name": "2025년 안전보건관리체계 구축 컨설팅",
        "category": "컨설팅",
        "agency": "고용노동부",
        "target": "중소사업장",
        "period": "2025-02-28 ~ 2025-12-31",
        "support_amount": "컨설팅",
        "keywords": ["안전", "보건", "건설안전", "산업안전"]
    },
    {
        "id": 6,
        "name": "2025년 기업부설연구소 설립지원",
        "category": "R&D",
        "agency": "과학기술정보통신부",
        "target": "중소기업",
        "period": "2025-01-01 ~ 2025-12-31",
        "support_amount": "최대 3억원",
        "keywords": ["연구소", "R&D", "기술개발"]
    },
    {
        "id": 7,
        "name": "2025년 스마트공장 고도화 지원사업",
        "category": "제조",
        "agency": "중소벤처기업부",
        "target": "제조중소기업",
        "period": "2025-01-01 ~ 2025-11-30",
        "support_amount": "최대 1억원",
        "keywords": ["스마트팩토리", "자동화", "디지털전환", "IoT"]
    },
    {
        "id": 8,
        "name": "2025년 농업기술 실용화 지원사업",
        "category": "농업",
        "agency": "농림축산식품부",
        "target": "농업법인",
        "period": "2025-03-01 ~ 2025-10-31",
        "support_amount": "최대 5억원",
        "keywords": ["농업기술", "스마트팜", "실용화"]
    },
    {
        "id": 9,
        "name": "2025년 의료기기 허가 지원사업",
        "category": "의료",
        "agency": "식품의약품안전처",
        "target": "의료기기기업",
        "period": "2025-01-01 ~ 2025-12-31",
        "support_amount": "허가컨설팅",
        "keywords": ["의료기기", "허가", "인허가"]
    },
    {
        "id": 10,
        "name": "2025년 친환경 에너지 전환 지원",
        "category": "에너지",
        "agency": "산업통상자원부",
        "target": "중소제조업",
        "period": "2025-02-01 ~ 2025-11-30",
        "support_amount": "최대 2억원",
        "keywords": ["에너지", "친환경", "탄소중립", "신재생"]
    },
    {
        "id": 11,
        "name": "2025년 AI·빅데이터 플랫폼 구축 지원",
        "category": "IT",
        "agency": "과학기술정보통신부",
        "target": "IT중소기업",
        "period": "2025-04-01 ~ 2025-12-31",
        "support_amount": "최대 3억원",
        "keywords": ["AI", "빅데이터", "플랫폼", "디지털"]
    },
    {
        "id": 12,
        "name": "2025년 수출 유망 중소기업 지정",
        "category": "수출",
        "agency": "중소벤처기업부",
        "target": "수출기업",
        "period": "2025-01-01 ~ 2025-12-31",
        "support_amount": "수출지원",
        "keywords": ["수출", "해외진출", "글로벌"]
    },
    {
        "id": 13,
        "name": "2025년 소부장 강소기업 100 육성",
        "category": "제조",
        "agency": "산업통상자원부",
        "target": "소재부품장비기업",
        "period": "2025-03-01 ~ 2025-10-31",
        "support_amount": "최대 10억원",
        "keywords": ["소재", "부품", "장비", "제조"]
    },
    {
        "id": 14,
        "name": "2025년 재활용 산업 육성 지원",
        "category": "환경",
        "agency": "환경부",
        "target": "재활용기업",
        "period": "2025-01-01 ~ 2025-12-31",
        "support_amount": "최대 5억원",
        "keywords": ["재활용", "순환경제", "폐기물", "자원순환"]
    },
    {
        "id": 15,
        "name": "2025년 바이오헬스 기술개발 지원",
        "category": "바이오",
        "agency": "보건복지부",
        "target": "바이오기업",
        "period": "2025-02-01 ~ 2025-11-30",
        "support_amount": "최대 7억원",
        "keywords": ["바이오", "헬스케어", "의료", "기술개발"]
    },
    {
        "id": 16,
        "name": "2025년 경영혁신형 중소기업(MAIN-BIZ) 육성",
        "category": "경영",
        "agency": "중소벤처기업부",
        "target": "중소기업",
        "period": "2025-01-01 ~ 2025-12-31",
        "support_amount": "컨설팅",
        "keywords": ["경영혁신", "컨설팅", "생산성"]
    },
    {
        "id": 17,
        "name": "2025년 하반기 기술창업 자금지원",
        "category": "창업",
        "agency": "중소벤처기업진흥공단",
        "target": "기술창업기업",
        "period": "2025-07-01 ~ 2025-12-31",
        "support_amount": "최대 5억원",
        "keywords": ["창업", "기술창업", "융자"]
    },
    {
        "id": 18,
        "name": "2025년 제조현장 IoT 보급확산 지원",
        "category": "제조",
        "agency": "산업통상자원부",
        "target": "제조중소기업",
        "period": "2025-03-01 ~ 2025-11-30",
        "support_amount": "최대 7천만원",
        "keywords": ["IoT", "센서", "제조", "자동화"]
    },
    {
        "id": 19,
        "name": "2025년 근로자 직업능력개발 지원",
        "category": "인력",
        "agency": "고용노동부",
        "target": "중소기업",
        "period": "2025-01-01 ~ 2025-12-31",
        "support_amount": "교육비",
        "keywords": ["교육", "훈련", "인력개발"]
    },
    {
        "id": 20,
        "name": "2025년 영세개인사업자 체납세금 징수특례",
        "category": "세제",
        "agency": "국세청",
        "target": "영세개인사업자",
        "period": "2020-01-01 ~ 2026-12-31",
        "support_amount": "세금 징수 특례",
        "keywords": ["세금", "체납", "특례"]
    }
]

# 요청 모델
class AnalyzeRequest(BaseModel):
    apiKey: str
    proposalText: str

class MatchRequest(BaseModel):
    apiKey: str
    n2bAnalysis: dict

@app.get("/")
async def root():
    return {"message": "N2B API Server is running", "version": "1.0.0"}

@app.post("/analyze")
async def analyze(request: AnalyzeRequest):
    """N2B 분석"""
    try:
        client = anthropic.Anthropic(api_key=request.apiKey)
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": f"""다음 사업계획서를 N2B(NOT-BUT-BECAUSE) 프레임워크로 분석해주세요.

사업계획서:
{request.proposalText}

다음 형식의 JSON으로만 답변해주세요:
{{
  "N": "현재의 문제점 (2-3문장)",
  "B": "제안하는 솔루션 (2-3문장)",
  "C": "근거 및 기대효과 (2-3문장)",
  "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"]
}}"""
            }]
        )
        
        # 응답 파싱
        text = message.content[0].text
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/match")
async def match(request: MatchRequest):
    """정부지원사업 매칭"""
    try:
        client = anthropic.Anthropic(api_key=request.apiKey)
        n2b = request.n2bAnalysis
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": f"""다음 N2B 분석 결과를 바탕으로, 제공된 정부지원사업 중 가장 적합한 3개를 추천해주세요.

N2B 분석:
- N (문제점): {n2b['N']}
- B (솔루션): {n2b['B']}
- C (근거): {n2b['C']}
- 키워드: {', '.join(n2b['keywords'])}

정부지원사업 목록:
{json.dumps(GOV_PROGRAMS, ensure_ascii=False, indent=2)}

다음 형식의 JSON으로만 답변해주세요:
{{
  "matches": [
    {{
      "program_id": 1,
      "score": 9,
      "reason": "추천 이유 (2-3문장)"
    }},
    {{
      "program_id": 2,
      "score": 8,
      "reason": "추천 이유 (2-3문장)"
    }},
    {{
      "program_id": 3,
      "score": 7,
      "reason": "추천 이유 (2-3문장)"
    }}
  ]
}}

매칭 점수는 1-10점으로 평가하고, 키워드 일치도, 사업 목적 부합도, 기대효과 등을 종합적으로 고려해주세요."""
            }]
        )
        
        # 응답 파싱
        text = message.content[0].text
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        
        # 프로그램 정보 추가
        for match in result["matches"]:
            program = next((p for p in GOV_PROGRAMS if p["id"] == match["program_id"]), None)
            match["program"] = program
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## 📋 requirements.txt
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
anthropic==0.7.8
pydantic==2.5.0
```

---

## 📋 Procfile

**새 파일 만들기 (확장자 없음):**
```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

---

## 🎯 다음 단계

### 1️⃣ GitHub 레포지토리 만들기
```
https://github.com/new

Repository name: n2b-backend
Public
Create repository
```

### 2️⃣ 파일 업로드
```
1. Add file → Create new file
2. 파일 이름: main.py
3. 위 코드 붙여넣기
4. Commit

5. Add file → Create new file
6. 파일 이름: requirements.txt
7. 위 내용 붙여넣기
8. Commit

9. Add file → Create new file
10. 파일 이름: Procfile
11. 위 내용 붙여넣기
12. Commit
