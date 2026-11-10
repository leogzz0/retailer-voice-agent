-- Runs once, on first start of an empty volume. Separate DB so tests never touch dev data.
CREATE DATABASE nopalia_test OWNER nopalia;
