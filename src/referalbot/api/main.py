from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import RedirectResponse
from sqladmin import Admin, ModelView
from sqladmin import action
from sqlalchemy import select, func
from src.referalbot.api.routes import router, log_to_google_sheet
from src.referalbot.database.db import async_session, init_db, engine
from src.referalbot.database.models import User, Purchase
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.orm import Session
import datetime
import asyncio

app = FastAPI()

# Инициализация шаблонов
templates = Jinja2Templates(directory="src/referalbot/api/templates")

class AdminAuth(AuthenticationBackend):
    def __init__(self, secret_key: str):
        super().__init__(secret_key=secret_key)

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username, password = form.get("username"), form.get("password")
        correct_username = "admin"
        correct_password = "admin123"
        if username == correct_username and password == correct_password:
            request.session.update({"token": "admin_token"})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")
        return token == "admin_token"

import os
templates_dir = os.path.abspath("src/referalbot/api/templates")

admin = Admin(
    app=app,
    engine=engine,
    authentication_backend=AdminAuth(secret_key="ddkdk22"),
    templates_dir=templates_dir,
   # templates_dir="src/referalbot/api/templates",
    base_url="/admin"
)

from sqlalchemy.orm import Session

class UserAdmin(ModelView, model=User):
    #detail_template = "custom_user_detail.html"
    #list_template = "custom_user_list.html"
    column_list = [
        User.id,
        User.telegram_id,
        User.username,
        User.promo_code,
        "invited_by.username",
        User.created_at,
        "referrals",
        "purchases",
    ]
    column_searchable_list = ["username", "promo_code", "telegram_id"]
    name = "Пользователь"
    name_plural = "Пользователи"
    icon = "fa fa-user"

    column_formatters = {
        "referrals": lambda model, attr: ", ".join([ref.username or f"User {ref.id}" for ref in model.referrals]) if model.referrals else "-",
        "purchases": lambda model, attr: ", ".join([p.name for p in model.purchases]) if model.purchases else "-",
        "invited_by.username": lambda model, attr: model.invited_by.username if model.invited_by else "-",
        "total_bonus": lambda model, attr: model.total_bonus,
        "paid_bonus": lambda model, attr: model.paid_bonus,
    }

    column_labels = {
        "referrals": "Рефералы",
        "purchases": "Покупки",
        "invited_by.username": "Пригласивший",
        "total_bonus": "Общий бонус",
        "paid_bonus": "Выплаченный бонус",
    }

    column_details_list = [
        "id",
        "telegram_id",
        "username",
        "promo_code",
        "invited_by.username",
        "created_at",
        "total_bonus",
        "paid_bonus",
    ]

    form_ajax_refs = {
        "invited_by": {
            "fields": ("username", "id"),
            "order_by": "username",
        }
    }

    @action(
        name="reset_bonus",
        label="Сбросить бонусы",
        confirmation_message="Вы уверены, что хотите сбросить бонусы для выбранных пользователей?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def reset_bonus_action(self, request):
        pks = request.query_params.getlist('pks')
        if not pks:
            return JSONResponse({"message": "Не выбраны пользователи"}, status_code=400)
        async with async_session() as session:
            for pk in pks:
                result = await session.execute(
                    select(Purchase).join(User, Purchase.user_id == User.id)
                    .filter(User.invited_by_id == int(pk), Purchase.bonus_paid == False)
                )
                purchases = result.scalars().all()
                for purchase in purchases:
                    purchase.bonus_paid = True
                    user = await session.execute(select(User).filter_by(id=purchase.user_id))
                    user = user.scalar_one_or_none()
                    if user:
                        log_to_google_sheet(purchase, user)
                await session.commit()
        return JSONResponse({"message": "Бонусы сброшены"})

    @action(
        name="delete_bonus",
        label="Удалить бонусы",
        confirmation_message="Вы уверены, что хотите удалить бонусы для выбранных пользователей?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def delete_bonus_action(self, request):
        pks = request.query_params.getlist('pks')
        if not pks:
            return JSONResponse({"message": "Не выбраны пользователи"}, status_code=400)
        async with async_session() as session:
            for pk in pks:
                result = await session.execute(
                    select(Purchase).join(User, Purchase.user_id == User.id)
                    .filter(User.invited_by_id == int(pk), Purchase.bonus_paid == False)
                )
                purchases = result.scalars().all()
                for purchase in purchases:
                    old_bonus = purchase.bonus_amount
                    purchase.bonus_amount = 0
                    print(f"Purchase {purchase.id}: bonus_amount {old_bonus} -> 0")
                    user = await session.execute(select(User).filter_by(id=purchase.user_id))
                    user = user.scalar_one_or_none()
                    if user:
                        log_to_google_sheet(purchase, user)
                await session.commit()
        return JSONResponse({"message": "Бонусы удалены"})

    @action(
        name="reduce_bonus",
        label="Уменьшить бонусы",
        confirmation_message="Перейти к форме для уменьшения бонусов?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def reduce_bonus_action(self, request):
        pks = request.query_params.getlist('pks')
        if not pks:
            return JSONResponse({"message": "Не выбраны пользователи"}, status_code=400)
        pks_query = "&".join([f"pks={pk}" for pk in pks])
        redirect_url = f"/custom/reduce_bonus_form?{pks_query}"
        print(f"Redirecting to: {redirect_url}")
        return RedirectResponse(url=redirect_url, status_code=302)
    
    @property
    def total_bonus(self):
        with Session(engine) as session:
            result = session.execute(
                select(func.sum(Purchase.bonus_amount))
                .join(User, Purchase.user_id == User.id)
                .filter(User.invited_by_id == self.id)
            )
            return result.scalar() or 0

    @property
    def paid_bonus(self):
        with Session(engine) as session:
            result = session.execute(
                select(func.sum(Purchase.bonus_amount))
                .join(User, Purchase.user_id == User.id)
                .filter(User.invited_by_id == self.id, Purchase.bonus_paid == True)
            )
            return result.scalar() or 0

class PurchaseAdmin(ModelView, model=Purchase):
    column_list = [
        Purchase.id,
        Purchase.user_id,
        "user.username",
        Purchase.name,
        Purchase.amount,
        Purchase.discount_applied,
        Purchase.bonus_amount,
        Purchase.date,
        Purchase.bonus_paid,
    ]
    column_searchable_list = ["user_id"]
    name = "Покупка"
    name_plural = "Покупки"
    icon = "fa fa-shopping-cart"

    column_formatters = {
        "user": lambda model, attr: model.user.username if model.user else "-",
        "user.username": lambda model, attr: model.user.username if model.user else "-",
    }

    column_labels = {
        "user": "Пользователь",
        "user.username": "Имя пользователя",
    }

    #form_create_template = "templates/purchase_create.html"
    #form_edit_template = "templates/purchase_create.html"

    async def on_model_change(self, data: dict, model: Purchase, is_created: bool, request: Request) -> None:
        print(f"on_model_change called, is_created={is_created}, data={data}")
        user_id = data.get("user")
        if not user_id:
            print("Поле user не передано в форме")
            raise HTTPException(status_code=400, detail="user_id не указан")
        
        async with async_session() as session:
            user = await session.execute(select(User).filter_by(id=int(user_id)))
            user = user.scalar_one_or_none()
            if not user:
                print(f"Пользователь не найден для user_id={user_id}")
                raise HTTPException(status_code=404, detail="Пользователь не найден")
            
            model.user_id = int(user_id)
            model.bonus_amount = int(round(int(data.get("amount", 0)) * 0.05)) if user.invited_by_id else 0
            print(f"Set bonus_amount={model.bonus_amount} for amount={data.get('amount')}, user_id={model.user_id}")

    async def get_form_data(self, request: Request):
        data = await super().get_form_data(request)
        async with async_session() as session:
            users = (await session.execute(select(User))).scalars().all()
        data["users"] = users
        return data

@app.get("/custom/reduce_bonus_form", response_class=HTMLResponse)
async def reduce_bonus_form(request: Request):
    print(f"Redirected to /custom/reduce_bonus_form with query: {request.query_params}")
    return templates.TemplateResponse(
        "reduce_bonus_form.html",
        {"request": request}
    )

@app.post("/custom/reduce_bonus", response_class=HTMLResponse)
async def reduce_bonus(request: Request):
    form = await request.form()
    amount = int(form.get("amount", 100))
    pks = form.getlist("pks")
    if not pks:
        return templates.TemplateResponse(
            "reduce_bonus_success.html",
            {"request": request, "message": "Не выбраны пользователи"}
        )
    async with async_session() as session:
        for pk in pks:
            result = await session.execute(
                select(Purchase).join(User, Purchase.user_id == User.id)
                .filter(User.invited_by_id == int(pk), Purchase.bonus_paid == False)
            )
            purchases = result.scalars().all()
            for purchase in purchases:
                old_bonus = purchase.bonus_amount
                purchase.bonus_amount = max(purchase.bonus_amount - amount, 0)
                print(f"Purchase {purchase.id}: bonus_amount {old_bonus} -> {purchase.bonus_amount}")
                user = await session.execute(select(User).filter_by(id=purchase.user_id))
                user = user.scalar_one_or_none()
                if user:
                    log_to_google_sheet(purchase, user)
            await session.commit()
    return templates.TemplateResponse(
        "reduce_bonus_success.html",
        {"request": request, "message": f"Бонусы уменьшены на {amount}"}
    )

admin.add_view(UserAdmin)
admin.add_view(PurchaseAdmin)

app.include_router(router)

@app.on_event("startup")
async def startup_event():
    await init_db()