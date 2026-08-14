(() => {
  const DAY_MS = 86400000;
  const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'];

  const toDate = (value) => {
    if (value instanceof Date) return new Date(value.getFullYear(), value.getMonth(), value.getDate(), 12);
    const [year, month, day] = String(value || '').split('-').map(Number);
    return year && month && day ? new Date(year, month - 1, day, 12) : null;
  };
  const toISO = (value) => value
    ? `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
    : '';
  const dayDistance = (left, right) => Math.round(Math.abs(left - right) / DAY_MS);
  const sameDay = (left, right) => Boolean(left && right && toISO(left) === toISO(right));
  const between = (value, left, right) => {
    if (!value || !left || !right) return false;
    const low = left < right ? left : right;
    const high = left < right ? right : left;
    return value >= low && value <= high;
  };

  class DateRangePicker extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({mode: 'open'});
      this.start = null;
      this.end = null;
      this.maxDate = null;
      this.maxDays = 0;
      this.cursor = new Date(new Date().getFullYear(), new Date().getMonth(), 1, 12);
      this.selecting = false;
      this.anchor = null;
      this.hovered = null;
      this.open = false;
      this._outside = (event) => { if (!this.contains(event.target)) this.close(); };
      this._escape = (event) => { if (event.key === 'Escape') this.close(); };
    }

    connectedCallback() {
      this.render();
      document.addEventListener('pointerdown', this._outside);
      document.addEventListener('keydown', this._escape);
    }

    disconnectedCallback() {
      document.removeEventListener('pointerdown', this._outside);
      document.removeEventListener('keydown', this._escape);
    }

    setConstraints({maxDate = null, maxDays = 0} = {}) {
      this.maxDate = toDate(maxDate);
      this.maxDays = Number(maxDays || 0);
      this.render();
    }

    setRange(start, end, {silent = true} = {}) {
      this.start = toDate(start);
      this.end = toDate(end);
      const focus = this.end || this.start || this.maxDate || new Date();
      this.cursor = new Date(focus.getFullYear(), focus.getMonth(), 1, 12);
      this.selecting = false;
      this.anchor = null;
      this.hovered = null;
      this.render();
      if (!silent) this.emitChange();
    }

    getRange() {
      if (!this.start || !this.end) return null;
      return {start: toISO(this.start), end: toISO(this.end), days: dayDistance(this.start, this.end) + 1};
    }

    emitChange() {
      const detail = this.getRange();
      if (detail) this.dispatchEvent(new CustomEvent('rangechange', {detail, bubbles: true, composed: true}));
    }

    close() {
      if (!this.open) return;
      this.open = false;
      this.selecting = false;
      this.anchor = null;
      this.hovered = null;
      this.render();
    }

    choose(date) {
      if (!this.selecting) {
        this.selecting = true;
        this.anchor = date;
        this.hovered = date;
        this.updateSelectionStart(date);
        return;
      }
      const start = date < this.anchor ? date : this.anchor;
      const end = date < this.anchor ? this.anchor : date;
      if (this.maxDays && dayDistance(start, end) + 1 > this.maxDays) return;
      this.start = start;
      this.end = end;
      this.selecting = false;
      this.anchor = null;
      this.hovered = null;
      this.open = false;
      this.render();
      this.emitChange();
    }

    updateSelectionStart(date) {
      this.shadowRoot.querySelectorAll('.day').forEach((button) => {
        const cellDate = toDate(button.dataset.date);
        button.toggleAttribute('disabled', this.isDisabled(cellDate));
        button.classList.toggle('in-range', sameDay(cellDate, date));
        button.classList.toggle('endpoint', sameDay(cellDate, date));
      });

      const hint = this.shadowRoot.querySelector('.hint');
      if (hint) {
        hint.dataset.selecting = 'true';
        hint.textContent = `已选开始日期 ${toISO(date)} · 移动光标预览，点击结束日期`;
      }
    }

    updatePreview(date) {
      if (!this.selecting || sameDay(this.hovered, date)) return;

      this.hovered = date;
      this.shadowRoot.querySelectorAll('.day').forEach((button) => {
        const cellDate = toDate(button.dataset.date);
        const inRange = between(cellDate, this.anchor, date);
        const endpoint = sameDay(cellDate, this.anchor) || sameDay(cellDate, date);
        button.classList.toggle('in-range', inRange);
        button.classList.toggle('endpoint', endpoint);
      });
    }

    isDisabled(date) {
      if (this.maxDate && date > this.maxDate) return true;
      return Boolean(this.selecting && this.maxDays && dayDistance(this.anchor, date) + 1 > this.maxDays);
    }

    render() {
      const range = this.selecting && this.anchor
        ? [this.anchor, this.hovered || this.anchor]
        : [this.start, this.end];
      const monthStart = new Date(this.cursor.getFullYear(), this.cursor.getMonth(), 1, 12);
      const firstOffset = (monthStart.getDay() + 6) % 7;
      const gridStart = new Date(monthStart);
      gridStart.setDate(gridStart.getDate() - firstOffset);
      const canNext = !this.maxDate || new Date(this.cursor.getFullYear(), this.cursor.getMonth() + 1, 1, 12) <= new Date(this.maxDate.getFullYear(), this.maxDate.getMonth(), 1, 12);
      const label = this.start && this.end ? `${toISO(this.start)}  →  ${toISO(this.end)}` : '选择开始和结束日期';
      const hint = this.selecting
        ? `已选开始日期 ${toISO(this.anchor)} · 移动光标预览，点击结束日期`
        : (this.maxDays ? `点击开始日期，再选择结束日期 · 最长 ${this.maxDays} 天` : '点击开始日期，再选择结束日期');

      const days = Array.from({length: 42}, (_, index) => {
        const date = new Date(gridStart);
        date.setDate(gridStart.getDate() + index);
        const outside = date.getMonth() !== this.cursor.getMonth();
        const disabled = this.isDisabled(date);
        const inRange = between(date, range[0], range[1]);
        const endpoint = sameDay(date, range[0]) || sameDay(date, range[1]);
        return `<button class="day${outside ? ' outside' : ''}${inRange ? ' in-range' : ''}${endpoint ? ' endpoint' : ''}" type="button" data-date="${toISO(date)}" ${disabled ? 'disabled' : ''} aria-label="${toISO(date)}">${date.getDate()}</button>`;
      }).join('');

      this.shadowRoot.innerHTML = `
        <style>
          :host{position:relative;display:inline-block;min-width:270px;font-family:var(--mono,"Cascadia Code",Consolas,monospace);color:var(--ink,#f0f2ec)}
          *{box-sizing:border-box}button{font:inherit}.trigger{display:grid;grid-template-columns:18px 1fr 18px;align-items:center;gap:9px;width:100%;min-height:34px;padding:0 10px;border:1px solid var(--line-strong,#3b423c);color:var(--mint,#9bf2c7);background:var(--surface,#0b0e0c);cursor:pointer;text-align:left;transition:border-color .18s,box-shadow .18s}.trigger:hover,.trigger[aria-expanded="true"]{border-color:var(--mint,#9bf2c7);box-shadow:0 0 0 3px rgba(155,242,199,.05)}.calendar-icon{width:13px;height:13px;border:1px solid currentColor;position:relative}.calendar-icon:before{content:"";position:absolute;left:-1px;right:-1px;top:3px;border-top:1px solid currentColor}.chevron{color:var(--muted,#727a73);font-size:12px}.value{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px;letter-spacing:.02em}
          .popover{position:absolute;z-index:100;top:calc(100% + 8px);right:0;width:332px;padding:14px;border:1px solid var(--line-strong,#3b423c);background:#090c0a;box-shadow:0 24px 70px rgba(0,0,0,.68),0 0 0 1px rgba(155,242,199,.025);animation:reveal .16s ease-out both}.popover:before{content:"";position:absolute;right:18px;top:-5px;width:8px;height:8px;border-left:1px solid var(--line-strong,#3b423c);border-top:1px solid var(--line-strong,#3b423c);background:#090c0a;transform:rotate(45deg)}
          .calendar-head{display:grid;grid-template-columns:30px 1fr 30px;align-items:center;margin-bottom:12px}.month{text-align:center;color:var(--ink,#f0f2ec);font-size:12px;letter-spacing:.08em}.nav{height:28px;border:1px solid var(--line,#252a26);color:var(--muted,#727a73);background:transparent;cursor:pointer}.nav:hover:not(:disabled){border-color:var(--mint,#9bf2c7);color:var(--mint,#9bf2c7)}.nav:disabled{opacity:.2;cursor:not-allowed}
          .week,.grid{display:grid;grid-template-columns:repeat(7,1fr)}.week span{padding:7px 0;color:var(--muted,#727a73);font-size:9px;text-align:center}.day{position:relative;height:38px;border:0;color:var(--soft,#b7bdb5);background:transparent;cursor:pointer;font-size:10px}.day:hover:not(:disabled){color:var(--ink,#f0f2ec);background:rgba(155,242,199,.13);box-shadow:inset 0 0 0 1px rgba(155,242,199,.38)}.day.outside{color:#444b45}.day.in-range{color:var(--ink,#f0f2ec);background:rgba(155,242,199,.09);box-shadow:inset 0 1px rgba(155,242,199,.08),inset 0 -1px rgba(155,242,199,.08)}.day.endpoint{z-index:1;color:#07130d;background:var(--mint,#9bf2c7);box-shadow:0 0 18px rgba(155,242,199,.22)}.day:disabled{color:#343934;background:transparent;cursor:not-allowed;text-decoration:line-through;text-decoration-color:#4a504b}
          .hint{min-height:30px;margin-top:11px;padding:9px 10px;border-left:2px solid var(--mint,#9bf2c7);color:var(--muted,#727a73);background:rgba(155,242,199,.035);font-size:9px;line-height:1.55}.hint[data-selecting="true"]{color:var(--mint,#9bf2c7)}
          @keyframes reveal{from{opacity:0;transform:translateY(-5px)}to{opacity:1;transform:translateY(0)}}@media(max-width:520px){:host{width:100%;min-width:0}.popover{position:fixed;left:10px;right:10px;top:50%;width:auto;transform:translateY(-50%);animation:none}.popover:before{display:none}}
          @media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
        </style>
        <button class="trigger" type="button" aria-haspopup="dialog" aria-expanded="${this.open}"><i class="calendar-icon" aria-hidden="true"></i><span class="value">${label}</span><span class="chevron">${this.open ? '▲' : '▼'}</span></button>
        ${this.open ? `<section class="popover" role="dialog" aria-label="日期区间选择"><header class="calendar-head"><button class="nav prev" type="button" aria-label="上个月">←</button><strong class="month">${this.cursor.getFullYear()} / ${String(this.cursor.getMonth() + 1).padStart(2, '0')}</strong><button class="nav next" type="button" aria-label="下个月" ${canNext ? '' : 'disabled'}>→</button></header><div class="week">${WEEKDAYS.map(day => `<span>${day}</span>`).join('')}</div><div class="grid">${days}</div><div class="hint" data-selecting="${this.selecting}">${hint}</div></section>` : ''}
      `;

      this.shadowRoot.querySelector('.trigger').addEventListener('click', () => {
        this.open = !this.open;
        if (!this.open) { this.selecting = false; this.anchor = null; this.hovered = null; }
        this.render();
      });
      if (!this.open) return;
      this.shadowRoot.querySelector('.prev').addEventListener('click', () => {
        this.cursor = new Date(this.cursor.getFullYear(), this.cursor.getMonth() - 1, 1, 12);
        this.render();
      });
      this.shadowRoot.querySelector('.next').addEventListener('click', () => {
        this.cursor = new Date(this.cursor.getFullYear(), this.cursor.getMonth() + 1, 1, 12);
        this.render();
      });
      this.shadowRoot.querySelectorAll('.day:not(:disabled)').forEach((button) => {
        const date = toDate(button.dataset.date);
        button.addEventListener('click', () => this.choose(date));
        button.addEventListener('pointerenter', () => {
          this.updatePreview(date);
        });
      });
    }
  }

  if (!customElements.get('date-range-picker')) customElements.define('date-range-picker', DateRangePicker);
})();
