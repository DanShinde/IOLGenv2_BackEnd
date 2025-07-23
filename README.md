# IOLGenv2_BackEnd
 
.venv\Scripts\activate
<!-- cd IOLGenv2_BackEnd -->
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate

python manage.py collectstatic --noinput

python manage.py runserver 0.0.0.0:8005