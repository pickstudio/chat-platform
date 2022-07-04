FROM python:3.9

WORKDIR /code
COPY . /code/

RUN pip install -r requirements.txt

EXPOSE "9000"
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--reload"]