from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# Создаем базовый класс для наших моделей
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    first_name = Column(String)
    last_name = Column(String)
    address = Column(String)

    # Отношение к модели Post, создающее обратную связь
    posts = relationship("Post", back_populates="author")

class Post(Base):
    __tablename__ = 'posts'
    id = Column(Integer, primary_key=True)
    title = Column(String)
    content = Column(String)
    views_count = Column(Integer, default=0)
    user_id = Column(Integer, ForeignKey('users.id'))

    # Отношение к модели User
    author = relationship("User", back_populates="posts")

    def __str__(self) -> str:
        return f'Айди {self.id} Название {self.title} Количество просмотров {self.views_count}'

# Создаем движок и таблицы
engine = create_engine('sqlite:///my_database.db')
Base.metadata.create_all(engine)

# Создаем фабрику сессий
Session = sessionmaker(bind=engine)
session = Session()

# Создаем нового пользователя
our_id = 0
andrey = session.query(Post).filter(User.user_id==our_id).first()
print(*andrey.posts, sep='\n')

# Фиксируем все изменения
session.commit()

session.close()