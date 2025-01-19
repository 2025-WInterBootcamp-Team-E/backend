import asyncio

from fastapi import APIRouter, Depends, UploadFile, HTTPException
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.database.session import get_db
from app.config.azure.pronunciation_feedback import analyze_pronunciation_with_azure
from app.schemas.ResultResponseModel import ResultResponseModel
from app.services.feedback_service import get_value, get_avg_score
from app.models.sentence import Sentence
from app.config.openAI.openai_service import get_pronunciation_feedback, sse_generator_wrapper
from app.models.feedback import Feedback
from app.services.user_service import get_user

router = APIRouter(
    prefix="/feedback",
    tags=["Feedback"]
)

@router.post("/{user_id}/{sentence_id}", summary="발음 분석", description="Azure Speech SDK를 이용해 발음 평가 결과 반환 및 데이터 저장")
async def analyze_pronunciation_endpoint(
        user_id: int,
        sentence_id: int,
        audio_file: UploadFile,
        db: Session = Depends(get_db),
):
    try:
        sentence_entry = db.query(Sentence).filter_by(sentence_id=sentence_id, is_deleted=False).first()
        if not sentence_entry:
            raise HTTPException(status_code=404, detail="해당 문장을 찾을 수 없습니다.")
        text = sentence_entry.content
        print(f"[LOG] Sentence Content: {text}")
        audio_data = await audio_file.read()
        azure_result = await analyze_pronunciation_with_azure(text, audio_data)
        print(f"[LOG] Azure Result: {azure_result}")
        json_string = None
        result_properties = azure_result.get("result_properties", {})
        print(f"[LOG] Available keys in result_properties: {list(result_properties.keys())}")

        for key in result_properties:
            if "JsonResult" in str(key):
                json_string = result_properties[key]
                break
        if not json_string:
            raise HTTPException(status_code=400, detail="Azure 응답에 JsonResult 데이터가 없습니다.")

        keys = ["AccuracyScore", "FluencyScore", "CompletenessScore", "PronScore"]
        scores = {}
        for key in keys:
            try:
                scores[key] = get_value(key, json_string)
                print(f"[LOG] {key}: {scores[key]}")
            except ValueError as e:
                print(f"[ERROR] {e}")
                raise HTTPException(status_code=400, detail=f"키 {key}를 찾을 수 없습니다.")

        feedback_generator = get_pronunciation_feedback(azure_result)

        wrapped_stream = sse_generator_wrapper(
            generator=feedback_generator,
            user_id=user_id,
            sentence_id=sentence_id,
            db=db,
            scores=scores
        )
        return StreamingResponse(
            wrapped_stream,                # async generator
            media_type="text/event-stream" # SSE MIME
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[ERROR] {e}")
        raise HTTPException(status_code=500, detail=f"발음 평가 중 오류가 발생했습니다: {str(e)}")

@router.get("/{user_id}/{sentence_id}/score", summary="최근 발음 평가 결과 평균 점수 조회", description="특정 사용자의 최근 발음 평가 평균 점수 결과 조회")
def get_user_avg_score(user_id: int, db: Session = Depends(get_db)):
    feedbacks_score = get_avg_score(user_id, db)
    user = get_user(user_id, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return ResultResponseModel(code=200, message="상황 문장 목록 조회 성공", data=feedbacks_score)