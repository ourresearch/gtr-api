# dump full database schema

```heroku bash run
pg_dump $DATABASE_URL --schema-only -f full_schema.sql
curl --upload-file full_schema.sql https://transfer.sh/full_schema.sql
```
then it'll tell you what url you can go to to download the schema