from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.services.speech_service import get_sentences_by_situation
from app.models.sentence import Sentence
from app.models.feedback import Feedback
from app.schemas.feedback import PronunciationResultResponse
from app.schemas.ResultResponseModel import ResultResponseModel

# APIRouter 생성
router = APIRouter(
    prefix="/speech",
    tags=["Speech"]
)

# 상황 문장 목록 조회 API
@router.get("/situationType/all", summary="상황 문장 목록 조회", description="특정 상황 유형에 해당하는 모든 문장을 조회합니다.")
def fetch_sentences(situation: str, db: Session = Depends(get_db)):
    sentences = get_sentences_by_situation(situation, db)
    if not sentences:
        raise HTTPException(
            status_code=404,
            detail=f"No sentences found for situation: {situation}"
        )

    # 문장 목록 데이터 생성
    response_data = [sentence.content for sentence in sentences]
    return ResultResponseModel(code=200, message="상황 문장 목록 조회 성공", data=response_data)


# 문장 조회 API
@router.get("/{sentence_id}", summary="문장 조회", description="문장 ID를 기반으로 문장을 조회합니다.")
def fetch_sentence(sentence_id: int, db: Session = Depends(get_db)):
    # 문장 데이터 조회
    sentence = db.query(Sentence).filter(Sentence.sentence_id == sentence_id).first()
    if not sentence:
        raise HTTPException(status_code=404, detail="Sentence not found")

    # 응답 데이터 생성
    response_data = {
        "content": sentence.content,
        "situation": sentence.situation.value,  # Enum 값을 반환
        "voice_url": sentence.voice_url
    }
    return ResultResponseModel(code=200, message="문장 조회 성공", data=response_data)


# 발음 테스트 결과 반환 API
@router.post("/{user_id}/results", summary="발음 테스트 결과 반환", description="특정 사용자의 발음 테스트 결과를 반환합니다.")
def get_pronunciation_results(user_id: int, sentence_id: int, db: Session = Depends(get_db)):
    # Feedback 데이터 조회
    feedback = db.query(Feedback).filter(
        Feedback.user_id == user_id,
        Feedback.sentence_id == sentence_id,
        Feedback.is_deleted == False
    ).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found for the given user and sentence")

    # Sentence 데이터 조회
    sentence = db.query(Sentence).filter(Sentence.sentence_id == sentence_id).first()
    if not sentence:
        raise HTTPException(status_code=404, detail="Sentence not found")
    # 응답 데이터 생성
    response_data = PronunciationResultResponse(
        accuracy=feedback.accuracy,
        feedback=feedback.pronunciation_feedback,
        content=sentence.content
    )
    '''
    SQLAlchemy ORM 객체인 Feedback에서 accuracy 속성은
    데이터베이스에서 실제 값을 가져오기 전에는 InstrumentedAttribute 타입으로 유지됩니다. 
    즉, 워닝은 쿼리를 실행하지 않았거나, 객체가 적절히 로드되지 않았기 때문에 발생한 것
    '''
    return ResultResponseModel(code=200, message="발음 테스트 결과 반환 성공", data=response_data)