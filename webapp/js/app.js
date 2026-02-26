const App = {
    history: [],
    searchTimer: null,

    init() {
        // Initialize Telegram Web App
        if (window.Telegram?.WebApp) {
            window.Telegram.WebApp.ready();
            window.Telegram.WebApp.expand();
        }

        Cart.updateBadge();
        this.navigate('categories');
    },

    navigate(page, params = {}) {
        // Save catalog page number before navigating away
        if (this.history.length > 0) {
            const prev = this.history[this.history.length - 1];
            if (prev.page === 'products') {
                prev.params._restorePage = Catalog.currentPage;
            }
        }
        this.history.push({ page, params });
        this.renderPage(page, params);
    },

    back() {
        if (this.history.length > 1) {
            this.history.pop(); // remove current
            const prev = this.history[this.history.length - 1];
            this.renderPage(prev.page, prev.params);
        }
    },

    renderPage(page, params) {
        const backBtn = document.getElementById('btn-back');
        const title = document.getElementById('page-title');
        const searchBar = document.getElementById('search-bar');
        const cartBtn = document.getElementById('btn-cart');

        // Defaults
        backBtn.style.display = this.history.length > 1 ? 'block' : 'none';
        searchBar.style.display = 'none';
        cartBtn.style.display = 'block';

        switch (page) {
            case 'categories':
                title.textContent = 'Каталог';
                backBtn.style.display = 'none';
                searchBar.style.display = 'block';
                this.history = [{ page, params }]; // reset history
                Catalog.currentCategory = null;
                Catalog.searchQuery = '';
                document.getElementById('search-input').value = '';
                Catalog.renderCategories();
                break;

            case 'products':
                title.textContent = params.categoryName || 'Товары';
                searchBar.style.display = 'block';
                Catalog.currentCategory = params.categoryId;
                if (params._restorePage) {
                    Catalog.currentPage = params._restorePage;
                }
                Catalog.renderProducts(params.categoryId, params.categoryName, Catalog.currentPage);
                break;

            case 'product':
                title.textContent = 'Товар';
                ProductPage.render(params.id);
                break;

            case 'cart':
                title.textContent = 'Корзина';
                cartBtn.style.display = 'none';
                Cart.render();
                break;

            case 'checkout':
                title.textContent = 'Оформление';
                cartBtn.style.display = 'none';
                OrderPage.render();
                break;
        }
    },

    onSearch(query) {
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => {
            if (query.length >= 2 || query.length === 0) {
                Catalog.search(query);
            }
        }, 400);
    },
};

// Start
document.addEventListener('DOMContentLoaded', () => App.init());
