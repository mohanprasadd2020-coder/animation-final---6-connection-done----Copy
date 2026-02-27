CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  firstname VARCHAR(100),
  lastname VARCHAR(100),
  email VARCHAR(150) UNIQUE,
  password VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)INSERT INTO users (
    id,
    firstname,
    lastname,
    email,
    password,
    created_at
  )
VALUES (
    id:int,
    'firstname:varchar',
    'lastname:varchar',
    'email:varchar',
    'password:varchar',
    'created_at:timestamp'
  );
SHOW TABLES;
