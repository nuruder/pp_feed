const OrderPage = {
    render() {
        const items = Cart.getItems();
        if (items.length === 0) {
            App.navigate('cart');
            return;
        }

        const total = Cart.getTotal();
        const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user || {};
        const defaultName = [tgUser.first_name, tgUser.last_name].filter(Boolean).join(' ');

        const content = document.getElementById('content');
        content.innerHTML = `
            <div class="order-form">
                <div class="form-group">
                    <label>Ваше имя</label>
                    <input type="text" id="order-name" value="${defaultName}" placeholder="Имя" required>
                </div>
                <div class="form-group">
                    <label>Телефон</label>
                    <input type="tel" id="order-phone" placeholder="+34 600 000 000" required>
                </div>
            </div>
            <div class="cart-total">
                <span>Итого:</span>
                <span>${total.toFixed(2).replace('.', ',')}&euro;</span>
            </div>
            <button class="btn-primary" id="btn-submit-order" onclick="OrderPage.submit()">
                Подтвердить заказ
            </button>
        `;
    },

    async submit() {
        const nameInput = document.getElementById('order-name');
        const phoneInput = document.getElementById('order-phone');

        const name = nameInput.value.trim();
        const phone = phoneInput.value.trim();

        if (!name) {
            nameInput.style.borderColor = '#e74c3c';
            nameInput.focus();
            return;
        }
        if (!phone) {
            phoneInput.style.borderColor = '#e74c3c';
            phoneInput.focus();
            return;
        }

        const btn = document.getElementById('btn-submit-order');
        btn.disabled = true;
        btn.textContent = 'Отправка...';

        const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user || {};
        const items = Cart.getItems();

        try {
            const order = await API.createOrder({
                user_id: tgUser.id || 0,
                user_first_name: tgUser.first_name || null,
                user_last_name: tgUser.last_name || null,
                username: tgUser.username || null,
                customer_name: name,
                customer_phone: phone,
                items: items.map(i => ({
                    product_id: i.product_id,
                    size_label: i.size_label || null,
                    quantity: i.quantity,
                })),
            });

            Cart.clear();
            this.renderSuccess(order);
        } catch (e) {
            btn.disabled = false;
            btn.textContent = 'Подтвердить заказ';
            alert('Ошибка при оформлении заказа: ' + e.message);
        }
    },

    renderSuccess(order) {
        const content = document.getElementById('content');
        content.innerHTML = `
            <div class="order-success">
                <div class="order-success-icon">&#10003;</div>
                <h2>Заказ оформлен!</h2>
                <p>Заказ #${order.id} на сумму ${order.total.toFixed(2).replace('.', ',')}&euro;</p>
                <p>Менеджер свяжется с вами в ближайшее время.</p>
                <br>
                <button class="btn-primary" onclick="App.navigate('categories')">Вернуться в каталог</button>
            </div>
        `;
    },
};
