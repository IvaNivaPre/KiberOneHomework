import json
from datetime import datetime, timedelta, timezone
from app.database import SessionLocal, engine, Base
from app.models import (
    User, Group, Module, Lesson, AssignmentMaterial, Quiz, QuizQuestion, Submission, QuizResult
)
from app.auth import hash_password

def seed_database():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Check if already seeded
        existing_tutor = db.query(User).filter(User.username == "tutor").first()
        if existing_tutor:
            print("База данных уже содержит данные. Пропускаем повторное заполнение.")
            return

        print("Заполнение демонстрационными данными KIBERone...")

        # 1. Create Tutor Account
        tutor = User(
            username="tutor",
            password_hash=hash_password("kiber2026"),
            plain_password="kiber2026",
            full_name="Алексей Сергеевич (Тьютор KIBERone)",
            role="tutor"
        )
        db.add(tutor)
        db.commit()
        db.refresh(tutor)

        # 2. Create Group
        group = Group(
            name="Python Junior (Суббота 11:00)",
            description="Группа резидентов 10-12 лет. Изучение алгоритмов, синтаксиса Python и разработка 2D игр."
        )
        db.add(group)
        db.commit()
        db.refresh(group)

        # 3. Create Students
        students_data = [
            ("student1", "student123", "Максим Смирнов"),
            ("student2", "student123", "София Новикова"),
            ("student3", "student123", "Артем Васильев"),
            ("student4", "student123", "Елизавета Морозова"),
        ]

        students = []
        for uname, pwd, fname in students_data:
            s = User(
                username=uname,
                password_hash=hash_password(pwd),
                plain_password=pwd,
                full_name=fname,
                role="student",
                group_id=group.id
            )
            db.add(s)
            students.append(s)
        db.commit()

        # 4. Create Module 1
        mod1 = Module(
            group_id=group.id,
            title="Модуль 1: Основы синтаксиса и алгоритмов Python",
            description="Базовые конструкции: переменные, типы данных, условные операторы и логика",
            order=1
        )
        db.add(mod1)
        db.commit()
        db.refresh(mod1)

        # 5. Create Lessons in Module 1
        now = datetime.now(timezone.utc)
        lesson1 = Lesson(
            module_id=mod1.id,
            title="Урок 1: Переменные и ввод-вывод (print / input)",
            description=(
                "На этом занятии мы изучили базовые типы данных (str, int, float) и функции print() и input().\n\n"
                "ЗАДАНИЕ ДЛЯ ДОМАШНЕЙ РАБОТЫ:\n"
                "1. Напишите программу-визитку резидента KIBERone, которая запрашивает имя, возраст и любимый язык программирования.\n"
                "2. Программа должна красиво выводить полученные данные в консоль.\n"
                "3. Прикрепите файл скрипта (.py) или скопируйте код в текстовое поле."
            ),
            deadline=now + timedelta(days=5),
            order=1,
            has_homework=True
        )
        db.add(lesson1)

        lesson2 = Lesson(
            module_id=mod1.id,
            title="Урок 2: Условные конструкции if-elif-else и ветвление",
            description=(
                "Изучили ветвление алгоритмов с помощью if, elif и else, а также операции сравнения ==, !=, >, <.\n\n"
                "ЗАДАНИЕ ДЛЯ ДОМАШНЕЙ РАБОТЫ:\n"
                "Создать текстовый мини-квест 'Выбери свой кибер-путь'. Программа предлагает пользователю сделать выбор (налево/направо/прямо) и выводит разные концовки."
            ),
            deadline=now + timedelta(days=2),
            order=2,
            has_homework=True
        )
        db.add(lesson2)
        db.commit()
        db.refresh(lesson1)
        db.refresh(lesson2)

        # 6. Add Materials to Lesson 1
        mat1 = AssignmentMaterial(
            lesson_id=lesson1.id,
            material_type="file",
            title="Методичка урока: Переменные в Python (PDF)",
            description="Конспект занятия с примерами кода и шпаргалкой по типам данных",
            file_name="Lesson1_Python_Variables.pdf",
            file_url="/uploads/demo_lesson1_manual.pdf",
            file_size=2450000
        )
        mat2 = AssignmentMaterial(
            lesson_id=lesson1.id,
            material_type="link",
            title="Онлайн-тренажер кода (Repl.it)",
            description="Песочница для написания и тестирования программ без установки Python",
            external_link="https://replit.com/~"
        )
        mat3 = AssignmentMaterial(
            lesson_id=lesson1.id,
            material_type="text",
            title="Памятка по функциям print() и input()",
            description="Помните, что input() всегда возвращает строку! Для чисел используйте int(input())."
        )
        db.add_all([mat1, mat2, mat3])

        # 7. Add Quiz to Lesson 1
        quiz1 = Quiz(
            lesson_id=lesson1.id,
            title="Проверочный тест: Переменные и типы данных",
            description="Быстрый тест из 3 вопросов для закрепления материала",
            passing_score=70
        )
        db.add(quiz1)
        db.commit()
        db.refresh(quiz1)

        q1 = QuizQuestion(
            quiz_id=quiz1.id,
            question_text="Какая функция в Python используется для вывода информации на экран?",
            question_type="single",
            options_json=json.dumps(["input()", "print()", "write()", "console.log()"], ensure_ascii=False),
            correct_answers_json=json.dumps(["print()"], ensure_ascii=False),
            points=1,
            order=1
        )
        q2 = QuizQuestion(
            quiz_id=quiz1.id,
            question_text="Какие из перечисленных типов данных являются базовыми в Python? (выберите все)",
            question_type="multiple",
            options_json=json.dumps(["int (целое число)", "str (строка)", "float (вещественное число)", "character"], ensure_ascii=False),
            correct_answers_json=json.dumps(["int (целое число)", "str (строка)", "float (вещественное число)"], ensure_ascii=False),
            points=2,
            order=2
        )
        q3 = QuizQuestion(
            quiz_id=quiz1.id,
            question_text="Какой результат вернет операция: type('KIBERone')? Напишите тип.",
            question_type="text",
            options_json="[]",
            correct_answers_json=json.dumps(["str"], ensure_ascii=False),
            points=1,
            order=3
        )
        db.add_all([q1, q2, q3])
        db.commit()

        # 8. Add Submissions showcasing different statuses (GREEN, YELLOW, RED)
        
        # Student 1: REVIEWED & GRADED -> Green Checkmark
        sub1 = Submission(
            lesson_id=lesson1.id,
            student_id=students[0].id,
            status="reviewed",
            text_answer=(
                "# Программа-визитка резидента\n"
                "name = input('Как тебя зовут? ')\n"
                "age = int(input('Сколько тебе лет? ')\n"
                "print(f'Привет, {name}! В {age} лет ты уже настоящий программист KIBERone!')"
            ),
            grade="5+ (Отлично)",
            tutor_comment="Прекрасно выполнено! Использованы f-строки и преобразование int(). Молодец!",
            submitted_at=now - timedelta(days=2),
            reviewed_at=now - timedelta(days=1)
        )

        # Student 1 also passed the quiz!
        qr1 = QuizResult(
            quiz_id=quiz1.id,
            student_id=students[0].id,
            score=4,
            max_score=4,
            percentage=100,
            passed=True,
            answers_json="{}",
            submitted_at=now - timedelta(days=2)
        )

        # Student 2: SUBMITTED (Awaiting review) -> Yellow
        sub2 = Submission(
            lesson_id=lesson1.id,
            student_id=students[1].id,
            status="submitted",
            text_answer="Сделала домашнее задание по инструкции, проверила в Repl.it, всё работает без ошибок!",
            file_name="sofiya_hw1.py",
            file_url="/uploads/demo_sofiya_hw1.py",
            file_size=1200,
            submitted_at=now - timedelta(hours=3)
        )

        # Student 3 & 4: DID NOT SUBMIT -> RED Marker / Missing!

        db.add_all([sub1, qr1, sub2])
        db.commit()

        print("[OK] База данных успешно инициализирована тестовыми данными:")
        print("  - Тьютор: логин 'tutor', пароль 'kiber2026'")
        print("  - Ученик 1: логин 'student1', пароль 'student123' [ЗЕЛЕНАЯ ГАЛОЧКА: ДЗ проверено]")
        print("  - Ученик 2: логин 'student2', пароль 'student123' [ЖЕЛТЫЙ: ДЗ на проверке]")
        print("  - Ученик 3: логин 'student3', пароль 'student123' [КРАСНЫЙ: ДЗ не сдано]")

    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
