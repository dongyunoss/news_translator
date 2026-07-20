from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import stocks
from .translator import translate_article

app = FastAPI(title="주린이 뉴스 번역기")

# 브라우저 확장(chrome-extension://)과 배포된 프론트엔드에서 호출할 수 있게 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)


@app.post("/api/translate")
def translate(req: TranslateRequest):
    return translate_article(req.text)


@app.get("/api/stocks/{code}")
def quote(code: str):
    q = stocks.get_quote(code)
    if q is None:
        raise HTTPException(status_code=404, detail=f"unknown stock code: {code}")
    return q


@app.get("/api/stocks/{code}/chart")
def chart(code: str, range: str = "3m"):
    if range not in stocks.CHART_RANGES:
        raise HTTPException(status_code=400, detail=f"range must be one of {list(stocks.CHART_RANGES)}")
    c = stocks.get_chart(code, range)
    if c is None:
        raise HTTPException(status_code=404, detail=f"unknown stock code: {code}")
    return c


_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
