const Catalog = {
    currentCategory: null,
    currentPage: 1,
    searchQuery: '',
    searchTimer: null,
    selectedBrand: null,
    selectedSize: null,
    priceMin: null,
    priceMax: null,
    priceTimer: null,
    filters: null, // { brands: [], sizes: [], price_min, price_max }

    async renderCategories() {
        const content = document.getElementById('content');
        content.innerHTML = '<div class="loading">Загрузка</div>';

        try {
            const categories = await API.getCategories();
            if (categories.length === 0) {
                content.innerHTML = '<div class="empty-state">Категории не найдены</div>';
                return;
            }

            let html = '<div class="categories-grid">';
            categories.forEach(cat => {
                html += `
                    <div class="category-card" onclick="Catalog.openCategory(${cat.id}, '${cat.name.replace(/'/g, "\\'")}')">
                        <div class="category-name">${cat.name}</div>
                        <div class="category-count">${cat.products_count} товаров</div>
                    </div>
                `;
            });
            html += '</div>';
            content.innerHTML = html;
        } catch (e) {
            content.innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
        }
    },

    openCategory(id, name) {
        this.currentCategory = id;
        this.currentPage = 1;
        this.searchQuery = '';
        this.selectedBrand = null;
        this.selectedSize = null;
        this.priceMin = null;
        this.priceMax = null;
        this.filters = null;
        document.getElementById('search-input').value = '';
        App.navigate('products', { categoryId: id, categoryName: name });
    },

    resetFilters() {
        this.selectedBrand = null;
        this.selectedSize = null;
        this.priceMin = null;
        this.priceMax = null;
        this.currentPage = 1;
        this.renderProducts(this.currentCategory, '');
    },

    setBrandFilter(brandId) {
        this.selectedBrand = this.selectedBrand === brandId ? null : brandId;
        this.currentPage = 1;
        this.renderProducts(this.currentCategory, '');
    },

    setSizeFilter(size) {
        this.selectedSize = this.selectedSize === size ? null : size;
        this.currentPage = 1;
        this.renderProducts(this.currentCategory, '');
    },

    onPriceInput() {
        clearTimeout(this.priceTimer);
        this.priceTimer = setTimeout(() => {
            const minEl = document.getElementById('filter-price-min');
            const maxEl = document.getElementById('filter-price-max');
            const minVal = minEl?.value ? parseFloat(minEl.value) : null;
            const maxVal = maxEl?.value ? parseFloat(maxEl.value) : null;
            if (minVal !== this.priceMin || maxVal !== this.priceMax) {
                this.priceMin = minVal;
                this.priceMax = maxVal;
                this.currentPage = 1;
                this.renderProducts(this.currentCategory, '');
            }
        }, 600);
    },

    _hasActiveFilters() {
        return this.selectedBrand !== null || this.selectedSize !== null
            || this.priceMin !== null || this.priceMax !== null;
    },

    filtersOpen: false,

    toggleFilters() {
        this.filtersOpen = !this.filtersOpen;
        const body = document.getElementById('filters-body');
        const toggle = document.getElementById('filters-toggle');
        if (body) body.style.display = this.filtersOpen ? 'block' : 'none';
        if (toggle) toggle.textContent = this.filtersOpen ? '\u25B2' : '\u25BC';
    },

    _renderFilters() {
        if (!this.filters) return '';

        const { brands, sizes, price_min, price_max } = this.filters;
        const hasContent = brands.length > 1 || sizes.length > 1 || (price_min != null && price_max != null && price_min !== price_max);
        if (!hasContent) return '';

        const active = this._hasActiveFilters();
        const isOpen = this.filtersOpen || active;

        let html = '<div class="filters-section">';
        html += `<div class="filters-header" onclick="Catalog.toggleFilters()">`;
        html += `<span class="filters-title">Фильтры${active ? ' \u2022' : ''}</span>`;
        html += `<span class="filters-toggle" id="filters-toggle">${isOpen ? '\u25B2' : '\u25BC'}</span>`;
        html += '</div>';
        html += `<div class="filters-body" id="filters-body" style="display:${isOpen ? 'block' : 'none'}">`;

        // Price range
        if (price_min != null && price_max != null && price_min !== price_max) {
            html += '<div class="filter-group">';
            html += '<div class="filter-label">Цена</div>';
            html += '<div class="price-filter-row">';
            html += `<input type="number" id="filter-price-min" class="price-filter-input" placeholder="${Math.floor(price_min)}" min="${Math.floor(price_min)}" max="${Math.ceil(price_max)}" step="1" value="${this.priceMin !== null ? this.priceMin : ''}" oninput="Catalog.onPriceInput()">`;
            html += '<span class="price-filter-sep">&mdash;</span>';
            html += `<input type="number" id="filter-price-max" class="price-filter-input" placeholder="${Math.ceil(price_max)}" min="${Math.floor(price_min)}" max="${Math.ceil(price_max)}" step="1" value="${this.priceMax !== null ? this.priceMax : ''}" oninput="Catalog.onPriceInput()">`;
            html += '<span class="price-filter-currency">&euro;</span>';
            html += '</div></div>';
        }

        if (brands.length > 1) {
            html += '<div class="filter-group">';
            html += '<div class="filter-label">Бренд</div>';
            html += '<div class="filter-chips">';
            brands.forEach(b => {
                const sel = this.selectedBrand === b.id ? ' selected' : '';
                html += `<button class="filter-chip${sel}" onclick="Catalog.setBrandFilter(${b.id})">${b.name} <span class="filter-count">${b.count}</span></button>`;
            });
            html += '</div></div>';
        }

        if (sizes.length > 1) {
            html += '<div class="filter-group">';
            html += '<div class="filter-label">Размер</div>';
            html += '<div class="filter-chips">';
            sizes.forEach(s => {
                const sel = this.selectedSize === s.label ? ' selected' : '';
                html += `<button class="filter-chip${sel}" onclick="Catalog.setSizeFilter('${s.label.replace(/'/g, "\\'")}')">${s.label} <span class="filter-count">${s.count}</span></button>`;
            });
            html += '</div></div>';
        }

        if (active) {
            html += '<button class="filter-reset" onclick="Catalog.resetFilters()">Сбросить фильтры</button>';
        }

        html += '</div></div>';
        return html;
    },

    async renderProducts(categoryId, categoryName, page = 1) {
        const content = document.getElementById('content');
        content.innerHTML = '<div class="loading">Загрузка</div>';

        try {
            // Load filters (only first time or after search change)
            const filterParams = {};
            if (categoryId) filterParams.category_id = categoryId;
            if (this.searchQuery) filterParams.search = this.searchQuery;

            if (!this.filters) {
                this.filters = await API.getFilters(filterParams);
            }

            const params = { page, page_size: 20 };
            if (categoryId) params.category_id = categoryId;
            if (this.searchQuery) params.search = this.searchQuery;
            if (this.selectedBrand !== null) params.brand_id = this.selectedBrand;
            if (this.selectedSize !== null) params.size = this.selectedSize;
            if (this.priceMin !== null) params.price_min = this.priceMin;
            if (this.priceMax !== null) params.price_max = this.priceMax;

            const data = await API.getProducts(params);

            let html = this._renderFilters();

            if (data.items.length === 0) {
                html += '<div class="empty-state">Товары не найдены</div>';
                content.innerHTML = html;
                return;
            }

            html += '<div class="products-grid">';
            data.items.forEach(p => {
                const imgHtml = p.image_url
                    ? `<img src="${p.image_url}" alt="" loading="lazy">`
                    : '<div class="img-placeholder">?</div>';

                html += `
                    <div class="product-card" onclick="App.navigate('product', {id: ${p.id}})">
                        ${imgHtml}
                        <div class="product-card-info">
                            <div class="product-card-name">${p.name}</div>
                            <div class="product-card-prices">
                                <span class="price-current">${p.price.toFixed(2)}&euro;</span>
                                <span class="price-old">${p.price_old.toFixed(2)}&euro;</span>
                            </div>
                        </div>
                    </div>
                `;
            });
            html += '</div>';

            // Pagination
            if (data.pages > 1) {
                html += '<div class="pagination">';
                html += `<button ${page <= 1 ? 'disabled' : ''} onclick="Catalog.goToPage(${page - 1}, ${categoryId || 'null'}, '${(categoryName || '').replace(/'/g, "\\'")}')">&larr;</button>`;
                html += `<button disabled>${page} / ${data.pages}</button>`;
                html += `<button ${page >= data.pages ? 'disabled' : ''} onclick="Catalog.goToPage(${page + 1}, ${categoryId || 'null'}, '${(categoryName || '').replace(/'/g, "\\'")}')">&rarr;</button>`;
                html += '</div>';
            }

            content.innerHTML = html;
        } catch (e) {
            content.innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
        }
    },

    goToPage(page, categoryId, categoryName) {
        this.currentPage = page;
        this.renderProducts(categoryId, categoryName, page);
    },

    search(query) {
        this.searchQuery = query;
        this.currentPage = 1;
        this.selectedBrand = null;
        this.selectedSize = null;
        this.priceMin = null;
        this.priceMax = null;
        this.filters = null; // reload filters for new search
        this.renderProducts(this.currentCategory, '', 1);
    },
};
