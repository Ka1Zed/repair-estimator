import { useState } from "react";
import RoomPointsTable from "../components/RoomPointsTable";
// Подключаем визуальный редактор и список комнат
import RoomPolygonEditor from "../components/RoomPolygonEditor";
import RoomsList from "../components/RoomsList";
import { useProjectStore } from "../store/projectStore";

export default function ProjectCreatePage() {
  // Название проекта остается общим для всей страницы
  const [projectName, setProjectName] = useState("");

  // Достаем из стора данные об активной комнате и методы для её изменения
  const activeRoomIndex = useProjectStore((state) => state.activeRoomIndex);
  const activeRoom = useProjectStore((state) => state.rooms[activeRoomIndex]);
  const updateRoomName = useProjectStore((state) => state.updateRoomName);
  const setHeight = useProjectStore((state) => state.setHeight);

  const handleNext = () => {
    // Валидируем данные, используя значения из стора активной комнаты
    if (!projectName || !activeRoom.name || !activeRoom.height) {
      alert("Пожалуйста, заполните все поля!");
      return;
    }

    if (Number(activeRoom.height) <= 0) {
      alert("Высота потолка должна быть больше нуля!");
      return;
    }

    alert(
      `Супер! Данные сохранены.\nПроект: ${projectName}\nАктивная комната: ${activeRoom.name}`
    );
  };

  return (
    /* Flex-контейнер, чтобы список комнат встал слева, а формы и редактор — справа */
    <div style={{ display: "flex", gap: "30px", alignItems: "flex-start", width: "100%", maxWidth: "900px", padding: "20px", boxSizing: "border-box" }}>
      
      {/* ЛЕВАЯ КОЛОНКА: Наш новый список комнат */}
      <RoomsList />

      {/* ПРАВАЯ КОЛОНКА: Формы, визуальный редактор и таблица координат */}
      <div style={{ flexGrow: 1, color: "#fff" }}>
        <h2 style={{ marginTop: 0 }}>Создание проекта</h2>

        <div style={{ marginBottom: "15px" }}>
          <label>Название проекта:</label>
          <input
            type="text"
            placeholder="Например: Ремонт квартиры"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            style={{ width: "100%", padding: "6px", marginTop: "5px", background: "#333", color: "#fff", border: "1px solid #555", borderRadius: "4px" }}
          />
        </div>

        <div style={{ marginBottom: "15px" }}>
          <label>Название активного помещения:</label>
          <input
            type="text"
            placeholder="Например: Спальня"
            // Данные берутся из активной комнаты стора
            value={activeRoom.name}
            // Меняем имя прямо в массиве комнат стора
            onChange={(e) => updateRoomName(activeRoomIndex, e.target.value)}
            style={{ width: "100%", padding: "6px", marginTop: "5px", background: "#333", color: "#fff", border: "1px solid #555", borderRadius: "4px" }}
          />
        </div>

        <div style={{ marginBottom: "15px" }}>
          <label>Высота потолка помещения (м):</label>
          <input
            type="number"
            step="0.1"
            placeholder="2.7"
            // Высота берется из активной комнаты стора
            value={activeRoom.height}
            // Обновляем высоту активной комнаты
            onChange={(e) => setHeight(Number(e.target.value) || 0)}
            style={{ width: "100%", padding: "6px", marginTop: "5px", background: "#333", color: "#fff", border: "1px solid #555", borderRadius: "4px" }}
          />
        </div>

        {/* Наш визуальный SVG-редактор */}
        <div style={{ marginTop: "20px" }}>
          <RoomPolygonEditor />
        </div>

        {/* Таблица точек под ним */}
        <div style={{ marginTop: "20px" }}>
          <RoomPointsTable />
        </div>

        <button
          onClick={handleNext}
          style={{ padding: "10px 20px", cursor: "pointer", marginTop: "25px", background: "#5cba5c", color: "#fff", border: "none", borderRadius: "4px", fontWeight: "bold" }}
        >
          Перейти к рисованию
        </button>
      </div>
    </div>
  );
}