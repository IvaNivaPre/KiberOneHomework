// Client side scripts for KiberOne platform

document.addEventListener('DOMContentLoaded', () => {
    // File input filename display
    const fileInputs = document.querySelectorAll('input[type="file"]');
    fileInputs.forEach(input => {
        input.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) {
                const fileName = e.target.files[0].name;
                const parent = input.closest('div');
                let badge = parent.querySelector('.selected-file-badge');
                if (!badge) {
                    badge = document.createElement('div');
                    badge.className = 'selected-file-badge mt-2 text-xs font-bold text-purple-700 bg-purple-50 px-3 py-1.5 rounded-lg border border-purple-200 inline-block';
                    parent.appendChild(badge);
                }
                badge.innerHTML = `<i class="fa-solid fa-check mr-1.5 text-emerald-600"></i> Выбран файл: ${fileName}`;
            }
        });
    });
});
