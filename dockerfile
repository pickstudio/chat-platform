FROM python:3.9

WORKDIR /code
COPY . /code/

RUN pip install -r requirements.txt

EXPOSE "9000"
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:9000"]