from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, Response 
from starlette.responses import RedirectResponse
from sqladmin import Admin, ModelView
from sqladmin import action
from sqlalchemy import select, func
from src.referalbot.api.routes import router, log_to_google_sheet, log_bonus_history
from src.referalbot.database.db import async_session, init_db, engine
from src.referalbot.database.models import User, Purchase, BonusHistory
from src.referalbot.database import repository
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload
import datetime
from aiogram import Bot
from referalbot.config import TELEGRAM_TOKEN
import asyncio
import os

app = FastAPI()
templates = Jinja2Templates(directory="src/referalbot/api/templates")
bot = Bot(token=TELEGRAM_TOKEN) # Создаем экземпляр бота для отправки сообщений


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

templates_dir = os.path.abspath("src/referalbot/api/templates")

admin = Admin(
    app=app,
    engine=engine,
    authentication_backend=AdminAuth(secret_key="ddkdk22"),
    templates_dir=templates_dir,
    base_url="/admin"
)

class UserAdmin(ModelView, model=User):
    name = "Пользователь"
    name_plural = "Пользователи"
    icon = "fa-solid fa-user"
    column_list = [User.id, User.telegram_id, User.username, "available_bonus", "pending_bonus"]
    column_searchable_list = ["username", "promo_code", "telegram_id"]
    column_details_list = [
        User.id, User.telegram_id, User.username, User.promo_code,
        "invited_by", "referrals", "bonus_history", "available_bonus", "pending_bonus"
    ]
    
    column_formatters = {
        "referrals": lambda m, a: "<br>".join(
            [f"{ref.username} (ID: {ref.telegram_id})" for ref in m.referrals]
        ) if m.referrals else "-",
        "bonus_history": lambda m, a: "<br>".join(
            [f"{h.date.strftime('%Y-%m-%d')}: {h.amount:+,} IDR ({h.operation}, {h.status})"
             for h in sorted(m.bonus_history, key=lambda x: x.date, reverse=True)]
        ) if m.bonus_history else "Нет операций",
        "available_bonus": lambda m, a: f"{m.available_bonus:,}",
        "pending_bonus": lambda m, a: f"{m.pending_bonus:,}",
    }
    
    async def get_query_for_list(self, session, *args, **kwargs):
        """Запрос для списка пользователей с предзагрузкой истории бонусов."""
        return await session.execute(
            select(User).options(selectinload(User.bonus_history))
        )
    
    async def get_query_for_details(self, session, pk):
        """Запрос для детального просмотра с загрузкой связей"""
        return await session.execute(
            select(User)
            .options(
                selectinload(User.invited_by),
                selectinload(User.referrals),
                selectinload(User.bonus_history)
            )
            .filter_by(id=pk)
        )
        
    @action(
        name="reset_bonus",
        label="Сбросить бонусы",
        confirmation_message="Вы уверены? Это отметит все доступные бонусы как выплаченные.",
    )
    async def reset_bonus_action(self, request: Request):
        pks = request.query_params.getlist("pks")
        if not pks:
            return JSONResponse({"message": "Не выбраны пользователи"}, status_code=400)

        messages = []
        async with async_session() as session:
            async with session.begin():
                for pk in pks:
                    user_id = int(pk)
                    user = await session.get(User, user_id)
                    username = user.username if user else f"ID {user_id}"

                    balance_data = await repository.get_bonus_balance(session, user_id)
                    available_balance = balance_data['available_balance']

                    if available_balance <= 0:
                        messages.append(f"❌ Для пользователя {username}: нет доступных бонусов для выплаты.")
                        continue

                    await log_bonus_history(
                        session,
                        user_id,
                        -available_balance,
                        "Выплата (Админ)",
                        "Выплата всего доступного баланса"
                    )
                    messages.append(f"✅ Для пользователя {username}: выплачен доступный баланс в размере {available_balance:,} IDR.")

        return JSONResponse({"message": " ".join(messages)})

    @action(
        name="delete_bonus",
        label="Удалить бонусы",
        confirmation_message="Вы уверены, что хотите удалить бонусы для выбранных пользователей?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def delete_bonus_action(self, request: Request):
        pks = request.query_params.getlist('pks')
        if not pks:
            return JSONResponse({"message": "Не выбраны пользователи"}, status_code=400)

        messages = []
        async with async_session() as session:
            async with session.begin():
                for pk in pks:
                    user_id = int(pk)
                    user = await session.get(User, user_id)
                    username = user.username if user else f"ID {user_id}"

                    # We are deleting the entire available balance.
                    balance_data = await repository.get_bonus_balance(session, user_id)
                    available_balance = balance_data['available_balance']

                    if available_balance <= 0:
                        messages.append(f"❌ Для пользователя {username}: нет доступных бонусов для удаления.")
                        continue

                    # Log a single transaction to delete the entire available balance.
                    await log_bonus_history(
                        session,
                        user_id,
                        -available_balance,
                        "Удаление (Админ)",
                        "Полное удаление доступного баланса"
                    )
                    messages.append(f"✅ Для пользователя {username}: доступный баланс в размере {available_balance:,} IDR был удален.")

        return JSONResponse({"message": " ".join(messages)})

    @action(
        name="reduce_bonus",
        label="Списать бонусы",
        confirmation_message="Перейти к форме для списания бонусов?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def reduce_bonus_action(self, request: Request):
        pks = request.query_params.getlist('pks')
        if not pks:
            return JSONResponse({"message": "Не выбраны пользователи"}, status_code=400)
        pks_query = "&".join([f"pks={pk}" for pk in pks])
        redirect_url = f"/custom/reduce_bonus_form?{pks_query}"
        return RedirectResponse(url=redirect_url, status_code=302)

class PurchaseAdmin(ModelView, model=Purchase):
    name = "Покупка"
    name_plural = "Покупки"
    icon = "fa-solid fa-shopping-cart"
    
    column_list = [Purchase.id, "user", Purchase.name, Purchase.amount, Purchase.bonus_amount, Purchase.date]
    form_excluded_columns = [Purchase.bonus_amount, Purchase.date]

    async def create(self, request: Request) -> Response:
        if request.method == "GET":
            # --- ОТЛАДКА ---
            print("GET /create. Данные в сессии:", request.session.get("last_purchase_data"))
            
            # Получаем форму
            Form = await self.scaffold_form()
            # Получаем данные из сессии
            initial_data = request.session.get("last_purchase_data", {})
            # Создаем экземпляр формы с начальными данными
            # Убедитесь, что ключи в initial_data соответствуют именам полей формы
            # и значения являются строками.
            form = Form(request, data=initial_data) # <-- Передаем initial_data
            context = {"request": request, "model_view": self, "form": form}
            # Рендерим шаблон формы
            return await self.templates.render(self.create_template, context=context)

        # --- Обработка POST ---
        elif request.method == "POST":
            # --- ОТЛАДКА ---
            print("POST /create. Начало обработки.")
            
            # 1. Получаем данные формы
            form_data = await request.form()
            # --- ОТЛАДКА ---
            print("Данные формы (POST):", dict(form_data))
            
            # 2. Определяем действие
            save_action = form_data.get("save_action")
            # --- ОТЛАДКА ---
            print("Действие:", save_action)

            # 3. Создаем форму для валидации
            Form = await self.scaffold_form()
            form = Form(request, form_data)
            await form.validate() # Важно: валидируем форму

            # 4. Проверяем валидацию
            if not form.is_valid():
                # --- ОТЛАДКА ---
                print("Форма невалидна:", form.errors)
                # Если форма невалидна, снова показываем её с ошибками
                context = {"request": request, "model_view": self, "form": form}
                return await self.templates.render(self.create_template, context=context)

            # 5. Если форма валидна, создаем модель
            # Создаем экземпляр модели Purchase, но пока не сохраняем в БД
            model = self.model()
            # Заполняем модель данными из формы
            data = form.data  # Это словарь с проверенными данными
            # --- ОТЛАДКА ---
            print("Проверенные данные формы:", data)
            
            # Вызываем on_model_change для бизнес-логики (например, расчет bonus_amount)
            # Передаем data, model, is_created=True
            await self.on_model_change(data, model, is_created=True) # is_created=True для логики в on_model_change
            
            # Заполняем модель оставшимися данными (дата, бонусы уже рассчитаны в on_model_change)
            model.date = datetime.datetime.utcnow()
            # data может не содержать все поля, которые мы установили в on_model_change
            # Поэтому копируем их из модели
            for name, value in data.items():
                if name != "save_action": # Исключаем служебное поле
                    setattr(model, name, value)
                    
            # --- ОТЛАДКА ---
            print("Модель перед сохранением:", model.__dict__)

            # 6. Сохраняем модель в БД
            async with async_session() as session:
                session.add(model)
                await session.commit()
                await session.refresh(model) # Получаем ID
                # --- ОТЛАДКА ---
                print("Модель сохранена с ID:", model.id)
                
            # 7. Вызываем after_model_change для логики после сохранения (бонусы)
            # Передаем data, сохраненную модель, is_created=True
            await self.after_model_change(data, model, is_created=True, request=request)

            # 8. Определяем, куда редиректить
            if save_action == "save_and_add_another":
                # Сохраняем данные для предзаполнения следующей формы
                # Берем из сохраненной модели, так как data может быть неактуальным
                session_data = {
                    "user": str(model.user_id), # Преобразуем в строку
                    "name": model.name,
                    "amount": str(model.amount),
                    "discount_applied": str(model.discount_applied)
                    # bonus_amount и date не сохраняем
                }
                request.session["last_purchase_data"] = session_data
                # --- ОТЛАДКА ---
                print("'Save and add another' нажата. Сохраненные данные:", session_data)
                # Редиректим НАЗАД на страницу создания
                return RedirectResponse(request.url, status_code=303) # 303 See Other для правильного GET-запроса
                
            else: # save_action == "save" или не определено
                # Очищаем сессию
                request.session.pop("last_purchase_data", None)
                # --- ОТЛАДКА ---
                print("'Save' нажата или действие не определено. Данные из сессии очищены.")
                # Редиректим на страницу списка
                return RedirectResponse(self.url_path_for('list'), status_code=303)

# Обновите также list, чтобы избежать преждевременной очистки
    async def list(self, request: Request) -> Response:
    # --- ОТЛАДКА ---
        print("GET /list. Session contents:", request.session)
        # При переходе к списку очищаем сессию от временных данных
        # Но только если мы пришли сюда не из-за "Save and add another"
        # Так как в create мы сами управляем редиректом, здесь можно просто очистить.
        # Хотя, если пользователь перешел на список другим способом, очистка не повредит.
        if "last_purchase_data" in request.session:
            print("Возврат к списку. Очистка данных из сессии.")
            request.session.pop("last_purchase_data", None)
        return await super().list(request)

# Обновите after_model_change, чтобы он не пытался обрабатывать form_data снова
    async def after_model_change(self, data: dict, model: Purchase, is_created: bool, request: Request) -> None:
        print("after_model_change вызван. is_created:", is_created, "model.id:", model.id if model else None)
    
    # Эта логика теперь вызывается из нашего кастомного create
    # и не должна больше пытаться анализировать request.form()
    
        if not is_created or not model or model.bonus_amount <= 0:
            # --- ОТЛАДКА ---
            print("after_model_change: Условия не выполнены (is_created, model, bonus_amount). Выход.")
            return
            
        # --- Логика начисления бонусов ---
        async with async_session() as session:
            # Загружаем Purchase с пользователем и его пригласившим
            purchase_db = await session.get(Purchase, model.id, options=[selectinload(Purchase.user).selectinload(User.invited_by)])
            if not (purchase_db and purchase_db.user and purchase_db.user.invited_by):
                # --- ОТЛАДКА ---
                print("after_model_change: Пользователь или пригласивший не найдены.")
                return # Нет пригласившего, бонус не начисляем
                
            inviter = purchase_db.user.invited_by
            user = purchase_db.user
            
            # Логируем бонус в истории
            await log_bonus_history(
                session, inviter.id, model.bonus_amount,
                "Начисление", f"За покупку от {user.username}"
            )
            
            # Отправляем уведомление в Telegram
            if inviter.telegram_id:
                try:
                    await bot.send_message(
                        chat_id=inviter.telegram_id,
                        text=f"🎉 Вам начислен бонус: +{model.bonus_amount:,} IDR"
                    )
                    # --- ОТЛАДКА ---
                    print(f"Уведомление отправлено пользователю {inviter.telegram_id}")
                except Exception as e:
                    print(f"Ошибка отправки уведомления: {e}")
                    
            await session.commit()
            # --- ОТЛАДКА ---
            print("Бонусы успешно начислены и записаны в БД.")
    
    async def on_model_change(self, data: dict, model: Purchase, is_created: bool, request: Request) -> None:
        async with async_session() as session:
            user = await session.get(User, int(data.get("user")))
            if user and user.invited_by_id:
                model.bonus_amount = int(round(int(data.get("amount", 0)) * 0.05))
            else:
                model.bonus_amount = 0

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
    amount_to_reduce = int(form.get("amount", 0))
    pks = form.getlist("pks")
    messages = []

    if not pks:
        return templates.TemplateResponse(
            "reduce_bonus_success.html",
            {"request": request, "message": "Ошибка: Не выбраны пользователи."}
        )
    
    if amount_to_reduce <= 0:
        return templates.TemplateResponse(
            "reduce_bonus_success.html",
            {"request": request, "message": "Ошибка: Сумма для списания должна быть положительной."}
        )

    async with async_session() as session:
        async with session.begin():
            for pk in pks:
                user_id = int(pk)
                
                # Получаем актуальный доступный баланс
                balance_data = await repository.get_bonus_balance(session, user_id)
                available_balance = balance_data['available_balance']
                
                user = await session.get(User, user_id)
                username = user.username if user else f"ID {user_id}"

                # Проверяем, достаточно ли средств
                if available_balance < amount_to_reduce:
                    message = f"❌ Для пользователя {username}: Недостаточно бонусов для списания. " \
                              f"Доступно: {available_balance}, требуется: {amount_to_reduce}."
                    messages.append(message)
                    continue

                # Если средств достаточно, производим списание
                await log_bonus_history(
                    session,
                    user_id,
                    -amount_to_reduce,
                    "Списание (Админ)",
                    f"Списание через админ-панель"
                )
                messages.append(f"✅ Для пользователя {username}: Бонусы успешно списаны на {amount_to_reduce:,} IDR.")

    return templates.TemplateResponse(
        "reduce_bonus_success.html",
        {"request": request, "message": "\n".join(messages)}
    )

class BonusHistoryAdmin(ModelView, model=BonusHistory):
    can_create = False
    can_edit = False
    can_delete = False
    column_list = [BonusHistory.date, "user", BonusHistory.amount, BonusHistory.operation, BonusHistory.description]

    column_formatters = {
        "user": lambda m, a: f"{m.user.username} (ID: {m.user_id})" if m.user else f"ID: {m.user_id}"
    }
    
    async def get_query_for_list(self, session, *args, **kwargs):
        return await session.execute(
            select(self.model)
            .options(selectinload(BonusHistory.user))
        )
    
    async def get_query_for_details(self, session, pk):
        return await session.execute(
            select(self.model)
            .options(selectinload(BonusHistory.user))
            .filter_by(id=pk)
        )

admin.add_view(UserAdmin)
admin.add_view(PurchaseAdmin)
admin.add_view(BonusHistoryAdmin)

app.include_router(router)

@app.on_event("startup")
async def startup_event():
    await init_db()