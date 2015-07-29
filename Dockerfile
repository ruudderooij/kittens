FROM python:3-onbuild
EXPOSE 8888 8000
CMD ["python", "./kittens.py"]
