import express from 'express';
import cors from 'cors';
import path from 'path';

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(process.cwd(), 'public')));

export default app;
