const Catalog = {
    currentCategory: null,
    currentPage: 1,
    searchQuery: '',
    searchTimer: null,

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
        document.getElementById('search-input').value = '';
        App.navigate('products', { categoryId: id, categoryName: name });
    },

    async renderProducts(categoryId, categoryName, page = 1) {
        const content = document.getElementById('content');
        content.innerHTML = '<div class="loading">Загрузка</div>';

        try {
            const params = { page, page_size: 20 };
            if (categoryId) params.category_id = categoryId;
            if (this.searchQuery) params.search = this.searchQuery;

            const data = await API.getProducts(params);

            if (data.items.length === 0) {
                content.innerHTML = '<div class="empty-state">Товары не найдены</div>';
                return;
            }

            let html = '<div class="products-grid">';
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
                                <span class="price-current">&euro;${p.price.toFixed(2)}</span>
                                <span class="price-old">&euro;${p.price_old.toFixed(2)}</span>
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
        this.renderProducts(this.currentCategory, '', 1);
    },
};
