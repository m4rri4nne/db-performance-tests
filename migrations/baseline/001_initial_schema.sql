CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    country TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    status TEXT CHECK (status IN ('pending', 'paid', 'shipped', 'cancelled')),
    total NUMERIC(10, 2),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INT REFERENCES orders(id),
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    price NUMERIC(10, 2) NOT NULL
);

CREATE TABLE inventory (
    product_id INT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    stock INT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);