import uvicorn

if __name__ == "__main__":
    print("\n=======================================================")
    print(" [KIBERone] Запуск платформы домашних заданий")
    print(" Адрес веб-сайта: http://localhost:8000")
    print("=======================================================\n")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
