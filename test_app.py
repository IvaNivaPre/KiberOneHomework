import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import User, Submission, QuizResult

class KiberOnePlatformTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_01_homepage_redirects_to_login(self):
        res = self.client.get("/", follow_redirects=False)
        self.assertEqual(res.status_code, 303)
        self.assertEqual(res.headers["location"], "/login")

    def test_02_login_page_renders(self):
        res = self.client.get("/login")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Личный кабинет", res.text)
        self.assertIn("KIBERone", res.text)

    def test_03_tutor_login_and_dashboard(self):
        # Login as tutor
        login_res = self.client.post(
            "/login",
            data={"username": "tutor", "password": "kiber2026"},
            follow_redirects=False
        )
        self.assertEqual(login_res.status_code, 303)
        self.assertEqual(login_res.headers["location"], "/tutor/dashboard")
        
        cookie = login_res.cookies.get("kiberone_session")
        self.assertIsNotNone(cookie)

        # Access dashboard with cookie
        dash_res = self.client.get("/tutor/dashboard", cookies={"kiberone_session": cookie})
        self.assertEqual(dash_res.status_code, 200)
        self.assertIn("Кабинет преподавателя", dash_res.text)
        self.assertIn("Python Junior", dash_res.text)

    def test_04_tutor_group_matrix_traffic_light(self):
        # Login
        login_res = self.client.post(
            "/login",
            data={"username": "tutor", "password": "kiber2026"},
            follow_redirects=False
        )
        cookie = login_res.cookies.get("kiberone_session")

        # Access traffic light matrix for group 1
        matrix_res = self.client.get("/tutor/group/1/matrix", cookies={"kiberone_session": cookie})
        self.assertEqual(matrix_res.status_code, 200)
        self.assertIn("Светофор сдачи ДЗ", matrix_res.text)
        self.assertIn("СДАНО", matrix_res.text)
        self.assertIn("НЕ СДАНО", matrix_res.text)

    def test_05_student_login_and_dashboard(self):
        # Login as student1
        login_res = self.client.post(
            "/login",
            data={"username": "student1", "password": "student123"},
            follow_redirects=False
        )
        self.assertEqual(login_res.status_code, 303)
        self.assertEqual(login_res.headers["location"], "/student/dashboard")

        cookie = login_res.cookies.get("kiberone_session")

        dash_res = self.client.get("/student/dashboard", cookies={"kiberone_session": cookie})
        self.assertEqual(dash_res.status_code, 200)
        self.assertIn("Максим Смирнов", dash_res.text)
        self.assertIn("ВЫПОЛНЕНО", dash_res.text)

    def test_06_student_submit_homework(self):
        # Login as student3 (who hasn't submitted yet)
        login_res = self.client.post(
            "/login",
            data={"username": "student3", "password": "student123"},
            follow_redirects=False
        )
        cookie = login_res.cookies.get("kiberone_session")

        # Submit text answer for lesson 1
        submit_res = self.client.post(
            "/student/lesson/1/submit",
            data={"text_answer": "print('Привет KIBERone от Артема!')"},
            cookies={"kiberone_session": cookie},
            follow_redirects=False
        )
        self.assertEqual(submit_res.status_code, 303)

        # Check in DB
        user = self.db.query(User).filter(User.username == "student3").first()
        sub = self.db.query(Submission).filter(
            Submission.student_id == user.id,
            Submission.lesson_id == 1
        ).first()
        self.assertIsNotNone(sub)
        self.assertEqual(sub.status, "submitted")

    def test_07_tutor_grade_submission(self):
        # Login as tutor
        login_res = self.client.post(
            "/login",
            data={"username": "tutor", "password": "kiber2026"},
            follow_redirects=False
        )
        cookie = login_res.cookies.get("kiberone_session")

        # Find student3's submission
        user = self.db.query(User).filter(User.username == "student3").first()
        sub = self.db.query(Submission).filter(
            Submission.student_id == user.id,
            Submission.lesson_id == 1
        ).first()

        # Grade it
        grade_res = self.client.post(
            f"/tutor/submission/{sub.id}/grade",
            data={
                "grade": "5 (Отлично)",
                "tutor_comment": "Хорошая работа, задача решена верно!",
                "status_choice": "reviewed"
            },
            cookies={"kiberone_session": cookie},
            follow_redirects=False
        )
        self.assertEqual(grade_res.status_code, 303)

        self.db.refresh(sub)
        self.assertEqual(sub.status, "reviewed")
        self.assertEqual(sub.grade, "5 (Отлично)")

    def test_08_student_quiz_submission(self):
        # Login as student3
        login_res = self.client.post(
            "/login",
            data={"username": "student3", "password": "student123"},
            follow_redirects=False
        )
        cookie = login_res.cookies.get("kiberone_session")

        # Submit quiz 1 with correct answers
        quiz_res = self.client.post(
            "/student/quiz/1/submit",
            data={
                "question_1": "print()",
                "question_2": ["int (целое число)", "str (строка)", "float (вещественное число)"],
                "question_3": "str"
            },
            cookies={"kiberone_session": cookie},
            follow_redirects=False
        )
        self.assertEqual(quiz_res.status_code, 303)

        user = self.db.query(User).filter(User.username == "student3").first()
        qr = self.db.query(QuizResult).filter(
            QuizResult.student_id == user.id,
            QuizResult.quiz_id == 1
        ).first()
        self.assertIsNotNone(qr)
        self.assertEqual(qr.percentage, 100)
        self.assertTrue(qr.passed)


if __name__ == "__main__":
    unittest.main()
