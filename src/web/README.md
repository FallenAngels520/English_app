# English App Chat UI

ChatGPT 风格的聊天界面，基于 Next.js 14、Tailwind CSS 与 shadcn/ui 组件库，支持 Markdown、代码高亮、流式回复、本地会话保存、暗黑模式、会话列表等功能。

## 开发

```bash
cd web
npm install
npm run dev
```

打开浏览器访问 http://localhost:3000 体验页面。构建或生产模式运行：

```bash
npm run build
npm start
```

## 功能速览

- 左右对话气泡、Enter/Shift+Enter 输入体验。
- Markdown + 代码高亮渲染。
- Fetch 流式输出（可停止/重新生成）。
- 错误提示、重试按钮及重新生成功能。
- 会话列表、本地存储、暗黑模式快捷切换。
```
