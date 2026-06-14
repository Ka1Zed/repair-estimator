import { useState } from "react";
// Шаг 1: Подключили нашу новую таблицу
import RoomPointsTable from "../components/RoomPointsTable";

export default function ProjectCreatePage() {
  // Создаем "переменные" для хранения того, что вводит пользователь
  const [projectName, setProjectName] = useState("");
  const [roomName, setRoomName] = useState("");
  const [ceilingHeight, setCeilingHeight] = useState("");

  // Функция, которая сработает при клике на кнопку
  const handleNext = () => {
    // Та самая базовая валидация: проверяем, что все поля заполнены
    if (!projectName || !roomName || !ceilingHeight) {
      alert("Пожалуйста, заполните все поля!");
      return;
    }

    if (parseFloat(ceilingHeight) <= 0) {
      alert("Высота потолка должна быть больше нуля!");
      return;
    }

    // Если всё хорошо, пока просто выводим сообщение
    alert(
      `Супер! Данные сохранены.\nПроект: ${projectName}\nКомната: ${roomName}`,
    );
  };

  return (
    <div style={{ padding: "20px", maxWidth: "400px" }}>
      <h2>Создание проекта</h2>

      <div style={{ marginBottom: "15px" }}>
        <label>Название проекта:</label>
        <input
          type="text"
          placeholder="Например: Ремонт квартиры"
          value={projectName}
          onChange={(e) => setProjectName(e.target.value)}
          style={{ width: "100%", padding: "5px", marginTop: "5px" }}
        />
      </div>

      <div style={{ marginBottom: "15px" }}>
        <label>Название комнаты:</label>
        <input
          type="text"
          placeholder="Например: Спальня"
          value={roomName}
          onChange={(e) => setRoomName(e.target.value)}
          style={{ width: "100%", padding: "5px", marginTop: "5px" }}
        />
      </div>

      <div style={{ marginBottom: "15px" }}>
        <label>Высота потолка (м):</label>
        <input
          type="number"
          step="0.1"
          placeholder="2.7"
          value={ceilingHeight}
          onChange={(e) => setCeilingHeight(e.target.value)}
          style={{ width: "100%", padding: "5px", marginTop: "5px" }}
        />
      </div>

      {/* Выводим саму таблицу прямо перед кнопкой */}
      <RoomPointsTable />

      <button
        onClick={handleNext}
        style={{ padding: "10px 20px", cursor: "pointer", marginTop: "20px" }}
      >
        Перейти к рисованию
      </button>
    </div>
  );
}
