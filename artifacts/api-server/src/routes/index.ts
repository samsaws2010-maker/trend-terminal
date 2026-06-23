import { Router, type IRouter } from "express";
import healthRouter from "./health";
import stocksRouter from "./stocks";
import newsRouter from "./news";

const router: IRouter = Router();

router.use(healthRouter);
router.use(stocksRouter);
router.use(newsRouter);

export default router;
