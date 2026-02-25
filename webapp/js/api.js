const API = {
    // Base URL — same origin as the web app
    base: '/api/v1/webapp',

    async get(path, params = {}) {
        const url = new URL(this.base + path, window.location.origin);
        Object.entries(params).forEach(([k, v]) => {
            if (v !== null && v !== undefined && v !== '') {
                url.searchParams.set(k, v);
            }
        });
        const res = await fetch(url);
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        return res.json();
    },

    async post(path, body) {
        const res = await fetch(this.base + path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `API error: ${res.status}`);
        }
        return res.json();
    },

    getCategories() {
        return this.get('/categories');
    },

    getProducts(params) {
        return this.get('/products', params);
    },

    getProduct(id) {
        return this.get(`/products/${id}`);
    },

    createOrder(data) {
        return this.post('/orders', data);
    },
};
