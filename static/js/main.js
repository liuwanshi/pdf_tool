/**
 * 通用前端交互逻辑
 */

// 当前页面导航高亮
(function () {
    const path = window.location.pathname;
    document.querySelectorAll('.navbar .nav-link').forEach(link => {
        const href = link.getAttribute('href');
        if (href === path) {
            link.classList.add('active');
        } else if (path === '/' && href === '/') {
            link.classList.add('active');
        }
    });
})();
