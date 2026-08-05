import math
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import desc, or_

from common.exception import MyException
from constants.code_enum import SysCodeEnum
from model.datasource_models import Datasource
from model.db_connection_pool import get_db_pool
from model.db_models import TAiModel, TDataTraining
from model.schemas import DataTrainingItem
from services.embedding_service import generate_embedding

pool = get_db_pool()


async def page_data_training(
    page: int,
    size: int,
    question: Optional[str] = None,
    oid: int = 1,
) -> Dict[str, Any]:
    with pool.get_session() as session:
        query = (
            session.query(
                TDataTraining,
                Datasource.name.label("datasource_name"),
                TAiModel.name.label("advanced_application_name"),
            )
            .outerjoin(
                Datasource,
                TDataTraining.datasource == Datasource.id,
            )
            .outerjoin(
                TAiModel,
                TDataTraining.advanced_application == TAiModel.id,
            )
            .filter(TDataTraining.oid == oid)
        )
        if question:
            query = query.filter(
                TDataTraining.question.ilike(f"%{question}%")
            )

        total_count = query.count()
        total_pages = math.ceil(total_count / size) if size > 0 else 0
        offset = (page - 1) * size
        results = (
            query.order_by(desc(TDataTraining.create_time))
            .offset(offset)
            .limit(size)
            .all()
        )

        records = []
        for training, datasource_name, application_name in results:
            records.append(
                DataTrainingItem(
                    id=training.id,
                    question=training.question,
                    description=training.description,
                    datasource=training.datasource,
                    datasource_name=datasource_name,
                    advanced_application=(
                        training.advanced_application
                    ),
                    advanced_application_name=application_name,
                    enabled=training.enabled,
                    create_time=(
                        str(training.create_time)
                        if training.create_time
                        else None
                    ),
                )
            )

        return {
            "records": records,
            "total_count": total_count,
            "current_page": page,
            "total_pages": total_pages,
        }


async def create_training(
    data: Dict[str, Any],
    oid: int = 1,
) -> bool:
    question = data.get("question")
    if not question:
        raise MyException(
            SysCodeEnum.PARAM_ERROR,
            "Question cannot be empty",
        )

    datasource = data.get("datasource")
    advanced_application = data.get("advanced_application")
    # Generate embedding - 当前层只使用用户配置的在线模型
    embedding = await generate_embedding(question)
    with pool.get_session() as session:
        query = session.query(TDataTraining).filter(
            TDataTraining.question == question,
            TDataTraining.oid == oid,
        )
        if datasource and advanced_application:
            query = query.filter(
                or_(
                    TDataTraining.datasource == datasource,
                    TDataTraining.advanced_application
                    == advanced_application,
                )
            )
        elif datasource:
            query = query.filter(
                TDataTraining.datasource == datasource
            )
        elif advanced_application:
            query = query.filter(
                TDataTraining.advanced_application
                == advanced_application
            )

        if query.count() > 0:
            raise MyException(
                SysCodeEnum.PARAM_ERROR,
                "Training data already exists",
            )

        session.add(
            TDataTraining(
                oid=oid,
                question=question,
                description=data.get("description"),
                datasource=datasource,
                advanced_application=advanced_application,
                embedding=embedding,
                enabled=data.get("enabled", True),
                create_time=datetime.now(),
            )
        )
        session.commit()
        return True


async def update_training(
    data: Dict[str, Any],
    oid: int = 1,
) -> bool:
    question = data.get("question")

    with pool.get_session() as session:
        training_id = data.get("id")
        training = session.query(TDataTraining).filter(
            TDataTraining.id == training_id
        ).first()
        if not training:
            raise MyException(
                SysCodeEnum.PARAM_ERROR,
                "Training data not found",
            )

        # Check if question changed to update embedding
        embedding = None
        if question and question != training.question:
            # This should be done outside lock/transaction if possible, but here we are inside session
            # However, we can just await it? session is not async session, but we are in async function.
            # Ideally we shouldn't hold db session while doing network request.
            pass

    # Generate embedding if question changed (outside session)
    # We need to re-fetch to check? Or just check data.
    # To avoid complexity, let's query first, check, then generate, then update.

    # Refactored update logic:
    training_id = data.get("id")
    current_question = None
    with pool.get_session() as session:
        training = session.query(TDataTraining).filter(
            TDataTraining.id == training_id
        ).first()
        if not training:
            raise MyException(
                SysCodeEnum.PARAM_ERROR,
                "Training data not found",
            )

        current_question = training.question

    embedding = None
    if question and question != current_question:
        # 当前层只使用用户配置的在线模型
        embedding = await generate_embedding(question)

    with pool.get_session() as session:
        training = session.query(TDataTraining).filter(
            TDataTraining.id == training_id
        ).first()
        if training:
            if question:
                training.question = question
            if embedding:
                training.embedding = embedding
            training.description = data.get(
                "description",
                training.description,
            )
            training.datasource = data.get(
                "datasource",
                training.datasource,
            )
            training.advanced_application = data.get(
                "advanced_application",
                training.advanced_application,
            )
            training.enabled = data.get("enabled", training.enabled)
            session.commit()
            return True
        return False


async def delete_training(ids: list[int]) -> bool:
    with pool.get_session() as session:
        session.query(TDataTraining).filter(
            TDataTraining.id.in_(ids)
        ).delete(synchronize_session=False)
        session.commit()
        return True


async def enable_training(
    training_id: int,
    enabled: bool,
) -> bool:
    with pool.get_session() as session:
        training = session.query(TDataTraining).filter(
            TDataTraining.id == training_id
        ).first()
        if not training:
            raise MyException(
                SysCodeEnum.PARAM_ERROR,
                "Training data not found",
            )
        training.enabled = enabled
        session.commit()
        return True
