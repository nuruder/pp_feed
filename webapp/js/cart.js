const Cart = {
    KEY: 'pp_cart',

    getItems() {
        try {
            return JSON.parse(localStorage.getItem(this.KEY)) || [];
        } catch {
            return [];
        }
    },

    save(items) {
        localStorage.setItem(this.KEY, JSON.stringify(items));
        this.updateBadge();
    },

    add(product, size, quantity) {
        const items = this.getItems();
        const existing = items.find(
            i => i.product_id === product.id && i.size_label === size
        );
        if (existing) {
            existing.quantity += quantity;
        } else {
            items.push({
                product_id: product.id,
                name: product.name,
                image_url: product.image_url,
                price: product.price,
                size_label: size,
                quantity: quantity,
            });
        }
        this.save(items);
    },

    remove(index) {
        const items = this.getItems();
        items.splice(index, 1);
        this.save(items);
    },

    clear() {
        localStorage.removeItem(this.KEY);
        this.updateBadge();
    },

    getTotal() {
        return this.getItems().reduce((sum, i) => sum + i.price * i.quantity, 0);
    },

    getCount() {
        return this.getItems().reduce((sum, i) => sum + i.quantity, 0);
    },

    updateBadge() {
        const count = this.getCount();
        const badge = document.getElementById('cart-badge');
        if (badge) {
            badge.textContent = count;
            badge.style.display = count > 0 ? 'flex' : 'none';
        }
    },

    render() {
        const items = this.getItems();
        const content = document.getElementById('content');

        if (items.length === 0) {
            content.innerHTML = '<div class="cart-empty">Корзина пуста</div>';
            return;
        }

        let html = '';
        items.forEach((item, index) => {
            const imgHtml = item.image_url
                ? `<img src="${item.image_url}" alt="">`
                : '<div class="img-placeholder" style="width:60px;height:60px;border-radius:8px">?</div>';

            const sizeText = item.size_label ? `, р. ${item.size_label}` : '';
            html += `
                <div class="cart-item">
                    ${imgHtml}
                    <div class="cart-item-info">
                        <div class="cart-item-name">${item.name}</div>
                        <div class="cart-item-meta">${item.quantity} шт.${sizeText}</div>
                        <div class="cart-item-price">${(item.price * item.quantity).toFixed(2).replace('.', ',')}&euro;</div>
                    </div>
                    <button class="cart-item-remove" onclick="Cart.removeAndRefresh(${index})">&times;</button>
                </div>
            `;
        });

        const total = this.getTotal();
        html += `
            <div class="cart-total">
                <span>Итого:</span>
                <span>${total.toFixed(2).replace('.', ',')}&euro;</span>
            </div>
            <button class="btn-primary" onclick="App.navigate('checkout')">Оформить заказ</button>
        `;

        content.innerHTML = html;
    },

    removeAndRefresh(index) {
        this.remove(index);
        this.render();
    },
};
