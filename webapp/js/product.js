const ProductPage = {
    product: null,
    selectedSize: null,
    quantity: 1,
    currentSlide: 0,
    touchStartX: 0,

    async render(productId) {
        const content = document.getElementById('content');
        content.innerHTML = '<div class="loading">Загрузка</div>';

        try {
            this.product = await API.getProduct(productId);
            this.selectedSize = null;
            this.quantity = 1;
            this.currentSlide = 0;
            this.draw();
        } catch (e) {
            content.innerHTML = '<div class="empty-state">Товар не найден</div>';
        }
    },

    _getGalleryImages() {
        const p = this.product;
        const imgs = (p.images && p.images.length > 0) ? [...p.images] : [];
        // Ensure main image is first if not already in the list
        if (p.image_url) {
            if (!imgs.includes(p.image_url)) {
                imgs.unshift(p.image_url);
            } else if (imgs.indexOf(p.image_url) !== 0) {
                imgs.splice(imgs.indexOf(p.image_url), 1);
                imgs.unshift(p.image_url);
            }
        }
        return imgs;
    },

    _renderGallery() {
        const images = this._getGalleryImages();

        if (images.length === 0) {
            return '<div class="img-placeholder" style="aspect-ratio:1;border-radius:12px;margin-bottom:12px">?</div>';
        }

        if (images.length === 1) {
            return `<img src="${images[0]}" alt="${this.product.name}">`;
        }

        // Multi-image gallery
        let html = '<div class="gallery" id="product-gallery">';
        html += '<div class="gallery-track" id="gallery-track">';
        images.forEach((url, i) => {
            html += `<img src="${url}" alt="" class="gallery-slide" loading="${i === 0 ? 'eager' : 'lazy'}">`;
        });
        html += '</div>';

        // Dots
        html += '<div class="gallery-dots">';
        images.forEach((_, i) => {
            html += `<span class="gallery-dot${i === this.currentSlide ? ' active' : ''}" onclick="ProductPage.goToSlide(${i})"></span>`;
        });
        html += '</div>';

        // Arrows
        html += `<button class="gallery-arrow gallery-arrow-left" onclick="ProductPage.prevSlide()">&#8249;</button>`;
        html += `<button class="gallery-arrow gallery-arrow-right" onclick="ProductPage.nextSlide()">&#8250;</button>`;
        html += '</div>';

        return html;
    },

    goToSlide(idx) {
        const images = this._getGalleryImages();
        if (idx < 0) idx = images.length - 1;
        if (idx >= images.length) idx = 0;
        this.currentSlide = idx;

        const track = document.getElementById('gallery-track');
        if (track) track.style.transform = `translateX(-${idx * 100}%)`;

        // Update dots
        document.querySelectorAll('.gallery-dot').forEach((dot, i) => {
            dot.classList.toggle('active', i === idx);
        });
    },

    prevSlide() { this.goToSlide(this.currentSlide - 1); },
    nextSlide() { this.goToSlide(this.currentSlide + 1); },

    initGalleryTouch() {
        const gallery = document.getElementById('product-gallery');
        if (!gallery) return;

        gallery.addEventListener('touchstart', (e) => {
            this.touchStartX = e.touches[0].clientX;
        }, { passive: true });

        gallery.addEventListener('touchend', (e) => {
            const diff = this.touchStartX - e.changedTouches[0].clientX;
            if (Math.abs(diff) > 40) {
                if (diff > 0) this.nextSlide();
                else this.prevSlide();
            }
        }, { passive: true });
    },

    draw() {
        const p = this.product;
        const content = document.getElementById('content');

        const galleryHtml = this._renderGallery();

        const stockClass = p.in_stock ? 'stock-in' : 'stock-out';
        const stockText = p.in_stock ? `В наличии (${p.stock_quantity < 5 ? 'мало' : 'много'})` : 'Нет в наличии';

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

        content.innerHTML = `
            <div class="product-detail">
                ${galleryHtml}
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
            </div>
        `;

        this.initGalleryTouch();
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
