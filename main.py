from conf.celery import get_stellar_accounts_from_django_task

if __name__ == '__main__':
    i = 100
    while i != 0:
        get_stellar_accounts_from_django_task()
        i -= 1