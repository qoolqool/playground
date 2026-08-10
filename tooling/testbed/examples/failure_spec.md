# My Testbed

I want a testbed with a database and a web server.

## Services

- web: my-web-app
  - port 8080:80
  - needs postgres

- postgres
  - port 5432

## Notes

This should be quick to set up. No need for healthchecks or anything fancy.
Just make it work.
