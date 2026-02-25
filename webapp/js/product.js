const ProductPage = {
    product: null,
    selectedSize: null,
    quantity: 1,

    async render(productId) {
        const content = document.getElementById('content');
        content.innerHTML = '<div class="loading">Загрузка</div>';

        try {
            this.product = await API.getProduct(productId);
            this.selectedSize = null;
            this.quantity = 1;
            this.draw();
        } catch (e) {
            content.innerHTML = '<div class="empty-state">Товар не найден</div>';
        }
    },

    draw() {
        const p = this.product;
        const content = document.getElementById('content');

        const imgHtml = p.image_url
            ? `<img src="${p.image_url}" alt="${p.name}">`
            : '<div class="img-placeholder" style="aspect-ratio:1;border-radius:12px;margin-bottom:12px">?</div>';

        const stockClass = p.in_stock ? 'stock-in' : 'stock-out';
        const stockText = p.in_stock ? `В наличии (${p.stock_quantity} шт.)` : 'Нет в наличии';

        // Sizes
        const availableSizes = (p.sizes || []).filter(s => s.in_stock);
        const hasSizes = p.sizes && p.sizes.length > 0;
        let sizesHtml = '';

        if (hasSizes) {
            sizesHtml = '<div class="sizes-section">';
            sizesHtml += '<div class="sizes-label">Размер:</div>';
            sizesHtml += '<div class="sizes-grid">';
            p.sizes.forEach(s => {
                const disabled = !s.in_stock;
                const selected = this.selectedSize === s.size_label;
                const cls = disabled ? 'size-btn disabled' : (selected ? 'size-btn selected' : 'size-btn');
                const onclick = disabled ? '' : `onclick="ProductPage.selectSize('${s.size_label}')"`;
                sizesHtml += `<button class="${cls}" ${onclick}>${s.size_label}</button>`;
            });
            sizesHtml += '</div></div>';
        }

        // Need size selection?
        const needsSize = hasSizes && availableSizes.length > 0;
        const canAdd = p.in_stock && (!needsSize || this.selectedSize);

        // Description (truncated)
        let descHtml = '';
        if (p.description) {
            // Strip HTML tags for clean display
            const div = document.createElement('div');
            div.innerHTML = p.description;
            const text = div.textContent || div.innerText || '';
            if (text.trim()) {
                const short = text.trim().substring(0, 300);
                descHtml = `<div class="product-description">${short}${text.length > 300 ? '...' : ''}</div>`;
            }
        }

        content.innerHTML = `
            <div class="product-detail">
                ${imgHtml}
                <div class="product-detail-name">${p.name}</div>
                <div class="product-detail-prices">
                    <span class="price-current">&euro;${p.price.toFixed(2)}</span>
                    <span class="price-old">&euro;${p.price_old.toFixed(2)}</span>
                </div>
                <div class="product-detail-stock ${stockClass}">${stockText}</div>
                ${sizesHtml}
                <div class="quantity-row">
                    <button class="qty-btn" onclick="ProductPage.changeQty(-1)">−</button>
                    <span class="qty-value">${this.quantity}</span>
                    <button class="qty-btn" onclick="ProductPage.changeQty(1)">+</button>
                </div>
                <button class="btn-primary" id="btn-add-cart" ${canAdd ? '' : 'disabled'}
                    onclick="ProductPage.addToCart()">
                    ${!p.in_stock ? 'Нет в наличии' : (needsSize && !this.selectedSize ? 'Выберите размер' : 'В корзину')}
                </button>
                ${descHtml}
            </div>
        `;
    },

    selectSize(label) {
        this.selectedSize = label;
        this.quantity = 1;
        this.draw();
    },

    changeQty(delta) {
        const newQty = this.quantity + delta;
        if (newQty < 1) return;

        // Limit by stock
        let maxQty = this.product.stock_quantity || 1;
        if (this.selectedSize && this.product.sizes) {
            const sz = this.product.sizes.find(s => s.size_label === this.selectedSize);
            if (sz && sz.quantity > 0) maxQty = sz.quantity;
        }
        if (newQty > maxQty) return;

        this.quantity = newQty;
        this.draw();
    },

    addToCart() {
        if (!this.product || !this.product.in_stock) return;

        const hasSizes = this.product.sizes && this.product.sizes.length > 0;
        const availableSizes = (this.product.sizes || []).filter(s => s.in_stock);
        if (hasSizes && availableSizes.length > 0 && !this.selectedSize) return;

        Cart.add(this.product, this.selectedSize, this.quantity);

        // Visual feedback
        const btn = document.getElementById('btn-add-cart');
        if (btn) {
            btn.textContent = 'Добавлено!';
            btn.disabled = true;
            setTimeout(() => {
                btn.textContent = 'В корзину';
                btn.disabled = false;
            }, 1000);
        }
    },
};
